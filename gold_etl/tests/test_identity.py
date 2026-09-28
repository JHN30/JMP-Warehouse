"""Cross-season identity derivation, storage, and CLI routing."""

import contextlib
import io
import unittest
from unittest.mock import patch

from gold_etl import main
from gold_etl.identity import derive_clubs, derive_players
from gold_etl.loader import replace_identity_scope
from gold_etl.quality import check_identity_scope
from gold_etl.schema import GOLD_TABLES, IDENTITY_TABLES, columns, create_table_sql
from gold_etl.tests.test_gold import FakeConnection


def player(season="E2025", code="P", key="P", registration="1", club="A", **changes):
    row = dict(competition_code="E", season_code=season, registration_key=registration,
               person_key=key, person_code=code, name="Player", country_code=None,
               country_name=None, height_cm=None, weight_kg=None, birth_at=None,
               birth_country_code=None, birth_country_name=None, position=1,
               position_name="Guard", club_code=club, club_name="Alpha")
    row.update(changes)
    return row


def club(season="E2025", code="A", **changes):
    row = dict(competition_code="E", season_code=season, club_code=code,
               name="Alpha", crest_url=None, country_code=None, country_name=None)
    row.update(changes)
    return row


class SchemaTests(unittest.TestCase):
    def test_identity_contract(self):
        self.assertEqual(tuple(IDENTITY_TABLES), ("app_players", "app_club_identities"))
        self.assertEqual(GOLD_TABLES["app_players"].key,
                         ("competition_code", "person_code"))
        self.assertEqual(GOLD_TABLES["app_club_identities"].key,
                         ("competition_code", "club_code"))
        self.assertEqual(columns("app_players"), (
            "competition_code", "person_code", "name", "country_code", "country_name",
            "height_cm", "weight_kg", "birth_at", "birth_country_code",
            "birth_country_name", "position", "position_name", "first_season_code",
            "last_season_code", "seasons_played", "clubs"))
        self.assertEqual(columns("app_club_identities"), (
            "competition_code", "club_code", "name", "crest_url", "country_code",
            "country_name", "first_season_code", "last_season_code", "seasons_played"))
        self.assertIn('"clubs" JSONB NOT NULL', create_table_sql("app_players"))
        self.assertIn('"seasons_played" INTEGER NOT NULL',
                      create_table_sql("app_club_identities"))
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main.main(["--list-tables"]), 0)
        self.assertIn("app_players\napp_club_identities", output.getvalue())


class DerivationTests(unittest.TestCase):
    def test_players_latest_profile_distinct_seasons_and_clubs(self):
        rows = [player("E2024", registration="1", club="B", name="Old"),
                player("E2025", registration="2", club="A", name="Current",
                       position=2, position_name="Forward", club_name="New A"),
                player("E2025", registration="3", club="A", name="Current",
                       position=2, position_name="Forward", club_name="New A"),
                player("E2025", registration="4", club="C", club_name="New C")]
        self.assertEqual(derive_players(rows), derive_players(list(reversed(rows))))
        result = derive_players(rows)[0]
        self.assertEqual((result["person_code"], result["name"], result["position"],
                          result["seasons_played"]), ("P", "Player", 1, 2))
        self.assertEqual((result["first_season_code"], result["last_season_code"]),
                         ("E2024", "E2025"))
        self.assertEqual(result["clubs"], [
            {"seasonCode": "E2024", "clubCode": "B", "clubName": "Alpha"},
            {"seasonCode": "E2025", "clubCode": "A", "clubName": "New A"},
            {"seasonCode": "E2025", "clubCode": "C", "clubName": "New C"}])

    def test_player_latest_registration_and_nulls(self):
        rows = [player(registration="1", name="Old", country_code="RS"),
                player(registration="2", name=None, country_code=None, club=None)]
        result = derive_players(rows)[0]
        self.assertIsNone(result["name"])
        self.assertIsNone(result["country_code"])
        self.assertEqual(result["clubs"], [{"seasonCode": "E2025",
                                           "clubCode": "A", "clubName": "Alpha"}])
        self.assertEqual(derive_players([]), [])

    def test_player_codes_must_be_stable(self):
        for rows in ([player(code=None)],
                     [player("E2024", code="P"), player("E2025", code="Q")],
                     [player(key="A", code="P"), player(key="B", code="P")]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                derive_players(rows)

    def test_club_latest_profile_and_distinct_seasons(self):
        rows = [club("E2024", name="Old", crest_url="old"),
                club("E2025", name="New", crest_url=None, country_code="RS"),
                club("E2025", name="New", crest_url=None, country_code="RS")]
        result = derive_clubs(rows)[0]
        self.assertEqual((result["name"], result["crest_url"],
                          result["country_code"], result["seasons_played"]),
                         ("New", None, "RS", 2))
        self.assertEqual((result["first_season_code"], result["last_season_code"]),
                         ("E2024", "E2025"))
        self.assertEqual(derive_clubs([]), [])
        with self.assertRaises(ValueError):
            derive_clubs([club(), club(name="Different")])


class StorageTests(unittest.TestCase):
    def test_replace_empty_rerun_and_rollback(self):
        db = FakeConnection()
        row = derive_clubs([club()])[0]
        with patch("gold_etl.loader.read_identity_rows", return_value=[row]), \
                patch("psycopg2.extras.execute_values") as insert:
            self.assertEqual(replace_identity_scope(db, "app_club_identities", "E"), 1)
        insert.assert_called_once()
        self.assertEqual(db.statements[-1][1], ("E",))
        with patch("gold_etl.loader.read_identity_rows", return_value=[]), \
                patch("psycopg2.extras.execute_values") as insert:
            self.assertEqual(replace_identity_scope(db, "app_club_identities", "E"), 0)
        insert.assert_not_called()
        with patch("gold_etl.loader.read_identity_rows", return_value=[row]), \
                patch("psycopg2.extras.execute_values", side_effect=RuntimeError("insert")):
            with self.assertRaises(RuntimeError):
                replace_identity_scope(db, "app_club_identities", "E")
        self.assertEqual((db.commits, db.rollbacks), (2, 1))

    def test_quality_checks_complete_values(self):
        db = FakeConnection()
        expected = derive_players([player()])[0]
        with db.cursor() as cursor:
            db.table_exists = False
            self.assertIn("missing", check_identity_scope(cursor, "app_players", "E")[0])
            db.table_exists = True
            with patch("gold_etl.quality.read_identity_rows", return_value=[expected]), \
                    patch("gold_etl.quality._dict_rows", return_value=[]):
                self.assertIn("keys differ", check_identity_scope(cursor, "app_players", "E")[0])
            changed = {**expected, "clubs": [{"seasonCode": "E2025", "clubCode": "B"}]}
            with patch("gold_etl.quality.read_identity_rows", return_value=[expected]), \
                    patch("gold_etl.quality._dict_rows", return_value=[changed]):
                self.assertIn("values differ", check_identity_scope(cursor, "app_players", "E")[0])


class CliTests(unittest.TestCase):
    def test_global_identity_modes_run_once_and_read_only_modes_do_not_write(self):
        for flag, target in (("--dry-run", "read_identity_rows"),
                             ("--quality-only", "check_identity_scope"),
                             (None, "replace_identity_scope")):
            db = FakeConnection()
            output = io.StringIO()
            with self.subTest(flag=flag), \
                    patch("gold_etl.main.connect", return_value=db), \
                    patch(f"gold_etl.main.{target}", return_value=[] if flag else 1) as action, \
                    contextlib.redirect_stdout(output):
                args = ["-sc", "all", "-tb", "app_club_identities"]
                if flag:
                    args.append(flag)
                self.assertEqual(main.main(args), 0)
            action.assert_called_once()
            self.assertIn("Identity scope: all locally loaded Silver seasons", output.getvalue())
            self.assertEqual(db.readonly, bool(flag))
            self.assertFalse(any("DELETE FROM gold" in query for query, _ in db.statements))


if __name__ == "__main__":
    unittest.main()
