"""Transactional PS slice replacement and read-only comparison."""

import unittest
from unittest.mock import patch

from gold_etl.loader import replace_postseason_scope
from gold_etl.quality import check_postseason_scope
from gold_etl.schema import physical_name
from gold_etl.schema import columns


class Cursor:
    def __init__(self, connection):
        self.connection = connection
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, query, params=None):
        self.connection.queries.append((query, params))

    def fetchone(self):
        return ("gold.app_season_player_stats_misc" if self.connection.exists else None,)


class Connection:
    def __init__(self):
        self.queries = []
        self.writes = []
        self.commits = 0
        self.rollbacks = 0
        self.exists = True

    def __enter__(self):
        return self

    def __exit__(self, kind, *_):
        if kind:
            self.rollbacks += 1
        else:
            self.commits += 1
        return False

    def cursor(self):
        return Cursor(self)


class PostseasonStorageTests(unittest.TestCase):
    def test_named_columns_scoped_delete_and_rerun(self):
        db = Connection()
        name = "season_player_stats_misc"
        derived = {name: [{"phase_code": "PS", "mode": "accumulated",
                           "entry_ordinal": 0, "person_key": "P1",
                           "games_played": 2}]}

        def insert(_, query, values, page_size):
            db.writes.append((query, values, page_size))

        with patch("gold_etl.loader.read_postseason_rows", return_value=derived), \
                patch("psycopg2.extras.execute_values", side_effect=insert):
            self.assertEqual(replace_postseason_scope(db, name, "E", "E2025"), 1)
            self.assertEqual(replace_postseason_scope(db, name, "E", "E2025"), 1)
        self.assertEqual(db.commits, 2)
        self.assertEqual(len(db.writes), 2)
        self.assertIn('INSERT INTO gold."app_season_player_stats_misc"', db.writes[0][0])
        self.assertNotIn("load_id", db.writes[0][0])
        self.assertEqual(db.writes[0][1][0][columns(name).index("person_key")], "P1")
        deletes = [(q, p) for q, p in db.queries if q.startswith("DELETE")]
        self.assertEqual(len(deletes), 2)
        self.assertTrue(all("gold." in q and "phase_code = 'PS'" in q and
                            p == ("E", "E2025") for q, p in deletes))
        self.assertFalse(any(q.startswith(("DELETE FROM silver", "INSERT INTO silver"))
                             or "neon" in q.lower() for q, _ in db.queries))

    def test_empty_derived_scope_clears_old_ps(self):
        db = Connection()
        with patch("gold_etl.loader.read_postseason_rows",
                   return_value={"season_player_stats_misc": []}), \
                patch("psycopg2.extras.execute_values") as insert:
            self.assertEqual(replace_postseason_scope(
                db, "season_player_stats_misc", "E", "E2025"), 0)
        insert.assert_not_called()
        self.assertEqual((db.commits, db.rollbacks), (1, 0))
        self.assertEqual(len(db.queries), 1)

    def test_failed_insert_rolls_back_ps_slice(self):
        db = Connection()
        rows = {"season_player_stats_misc": [{"phase_code": "PS"}]}
        with patch("gold_etl.loader.read_postseason_rows", return_value=rows), \
                patch("psycopg2.extras.execute_values", side_effect=RuntimeError("failed")):
            with self.assertRaisesRegex(RuntimeError, "failed"):
                replace_postseason_scope(db, "season_player_stats_misc", "E", "E2025")
        self.assertEqual((db.commits, db.rollbacks), (0, 1))

    def test_quality_detects_missing_count_and_value_mismatch(self):
        db = Connection()
        name = "season_player_stats_misc"
        expected = {name: [{"mode": "accumulated", "entry_ordinal": 0,
                            "phase_code": "PS", "person_key": "A"}]}
        with db.cursor() as cursor:
            db.exists = False
            self.assertEqual(check_postseason_scope(cursor, name, "E", "E2025"),
                             [f"gold.{physical_name(name)} is missing"])
            db.exists = True
            with patch("gold_etl.quality.read_postseason_rows", return_value=expected), \
                    patch("gold_etl.quality._dict_rows", return_value=[]):
                issues = check_postseason_scope(cursor, name, "E", "E2025")
            self.assertIn("Silver derivation expects 1", issues[0])
            with patch("gold_etl.quality.read_postseason_rows", return_value=expected), \
                    patch("gold_etl.quality._dict_rows", return_value=[
                        {"mode": "accumulated", "entry_ordinal": 0,
                         "phase_code": "PS", "person_key": "B"}]):
                issues = check_postseason_scope(cursor, name, "E", "E2025")
            self.assertIn("derived keys or values differ", issues[0])


if __name__ == "__main__":
    unittest.main()
