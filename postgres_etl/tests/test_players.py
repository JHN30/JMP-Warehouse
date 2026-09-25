"""No database required: exercise the player-identity SQL shape and
dry-run/real-run safety with fakes, matching test_records.py's convention."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main as etl_main
from players import _INSERT_COLUMNS, _players_select_sql, build_players


class PlayersSqlTests(unittest.TestCase):
    def test_only_players_are_included_not_coaches_or_staff(self):
        sql = _players_select_sql()
        self.assertIn("role_code = 'J'", sql)
        # Every CTE that reads registrations restricts to players; count the
        # occurrences to make sure the filter wasn't dropped from one of them.
        self.assertEqual(sql.count("role_code = 'J'"), 3)

    def test_identity_fields_come_from_the_latest_season_per_player(self):
        sql = _players_select_sql()
        self.assertIn("DISTINCT ON (competition_code, person_code)", sql)
        self.assertIn("ORDER BY competition_code, person_code, season_code DESC", sql)

    def test_clubs_are_deduplicated_before_aggregating_and_ordered_by_season(self):
        sql = _players_select_sql()
        self.assertIn("SELECT DISTINCT competition_code, person_key, season_code, "
                      "club_code, club_name", sql)
        self.assertIn("jsonb_agg(jsonb_build_object(", sql)
        self.assertIn("ORDER BY season_code) AS clubs", sql)

    def test_insert_columns_match_the_select_output(self):
        self.assertEqual(_INSERT_COLUMNS, (
            "competition_code", "person_code", "name", "country_code", "country_name",
            "height_cm", "weight_kg", "birth_at", "birth_country_code", "birth_country_name",
            "position", "position_name", "first_season_code", "last_season_code",
            "seasons_played", "clubs",
        ))


class FakeCursor:
    def __init__(self, count=5):
        self.count = count
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, query, params=None):
        self.statements.append(query)

    def fetchone(self):
        return (self.count,)


class FakeConnection:
    def __init__(self, count=5):
        self.fake_cursor = FakeCursor(count=count)
        self.rolled_back = False

    def cursor(self):
        return self.fake_cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, *_):
        return False

    def set_session(self, **kwargs):
        pass

    def rollback(self):
        self.rolled_back = True

    def close(self):
        pass


class BuildPlayersTests(unittest.TestCase):
    def test_dry_run_never_truncates_or_inserts(self):
        connection = FakeConnection(count=3749)
        with patch("players.connect", return_value=connection):
            counts = build_players("unused", ["app_players"], dry_run=True)
        self.assertEqual(counts, {"app_players": 3749})
        statements = connection.fake_cursor.statements
        self.assertFalse(any("TRUNCATE" in s for s in statements))
        self.assertFalse(any(s.startswith("INSERT") for s in statements))
        self.assertTrue(connection.rolled_back)

    def test_real_run_truncates_then_inserts_then_counts(self):
        connection = FakeConnection(count=3749)
        with patch("players.connect", return_value=connection):
            counts = build_players("unused", ["app_players"], dry_run=False)
        statements = connection.fake_cursor.statements
        truncate_index = next(i for i, s in enumerate(statements) if "TRUNCATE TABLE" in s)
        insert_index = next(i for i, s in enumerate(statements) if s.startswith("INSERT INTO"))
        self.assertLess(truncate_index, insert_index)
        self.assertEqual(counts, {"app_players": 3749})

    def test_unknown_table_is_rejected(self):
        with self.assertRaises(ValueError):
            build_players("unused", ["not_a_player_table"])


class PlayersRoutingTests(unittest.TestCase):
    def test_players_only_selection_skips_the_flat_loader(self):
        with patch.object(etl_main, "available_seasons", return_value=["E2025"]), \
                patch.object(etl_main, "FlatDatabaseLoader") as loader, \
                patch.object(etl_main, "build_players", return_value={}) as build, \
                patch.object(etl_main, "validate_players", return_value=True) as validate:
            self.assertEqual(etl_main.main(["-sc", "2025", "-tb", "app_players"]), 0)
            loader.return_value.run.assert_not_called()
            build.assert_called_once()
            validate.assert_called_once()

    def test_quality_only_does_not_rebuild_players(self):
        with patch.object(etl_main, "available_seasons", return_value=["E2025"]), \
                patch.object(etl_main, "FlatDatabaseLoader") as loader, \
                patch.object(etl_main, "build_players") as build, \
                patch.object(etl_main, "validate_players", return_value=True) as validate:
            self.assertEqual(etl_main.main([
                "-sc", "2025", "-tb", "app_players", "--quality-only",
            ]), 0)
            loader.return_value.run.assert_not_called()
            build.assert_not_called()
            validate.assert_called_once()


if __name__ == "__main__":
    unittest.main()
