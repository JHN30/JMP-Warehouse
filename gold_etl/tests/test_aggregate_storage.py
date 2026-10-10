"""Atomic derived Gold storage and full-value read-only checks."""

import unittest
from unittest.mock import patch

from gold_etl.loader import replace_aggregate_scope
from gold_etl.quality import check_aggregate_scope
from gold_etl.schema import physical_name
from gold_etl.schema import AGGREGATE_NAMES, columns


class Cursor:
    def __init__(self, db):
        self.db = db

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, query, params=None):
        self.db.queries.append((query, params))

    def fetchone(self):
        return ("present" if self.db.exists else None,)


class Connection:
    def __init__(self):
        self.queries = []
        self.commits = 0
        self.rollbacks = 0
        self.exists = True

    def cursor(self):
        return Cursor(self)

    def __enter__(self):
        return self

    def __exit__(self, kind, *_):
        if kind:
            self.rollbacks += 1
        else:
            self.commits += 1
        return False


def row(name):
    value = {field: None for field in columns(name)}
    value.update(competition_code="E", season_code="E2025")
    if name == "app_team_season_stats":
        value.update(phase_code="RS", club_code="MAD", games_played=1)
    elif name == "app_coverage_games":
        value["game_code"] = 1
        value["items"] = []
    else:
        value["items"] = []
    return value


class AggregateStorageTests(unittest.TestCase):
    def test_replace_and_clear_each_scope(self):
        for name in AGGREGATE_NAMES:
            with self.subTest(name=name):
                db = Connection()
                writes = []
                with patch("gold_etl.loader.read_aggregate_rows", return_value=[row(name)]), \
                        patch("psycopg2.extras.execute_values",
                              side_effect=lambda _, sql, values, page_size:
                              writes.append((sql, values))):
                    self.assertEqual(replace_aggregate_scope(db, name, "E", "E2025"), 1)
                self.assertEqual(db.commits, 1)
                self.assertIn(f'INSERT INTO gold."{physical_name(name)}"', writes[0][0])
                if name.startswith("app_coverage"):
                    self.assertEqual(writes[0][1][0][columns(name).index("items")].adapted,
                                     [])
                self.assertTrue(any(query.startswith(f'DELETE FROM gold."{physical_name(name)}"')
                                    and params == ("E", "E2025")
                                    for query, params in db.queries))
                with patch("gold_etl.loader.read_aggregate_rows", return_value=[]), \
                        patch("psycopg2.extras.execute_values") as insert:
                    self.assertEqual(replace_aggregate_scope(db, name, "E", "E2025"), 0)
                insert.assert_not_called()
                self.assertEqual(db.commits, 2)

    def test_insert_failure_rolls_back(self):
        db = Connection()
        with patch("gold_etl.loader.read_aggregate_rows",
                   return_value=[row("app_team_season_stats")]), \
                patch("psycopg2.extras.execute_values", side_effect=RuntimeError("failed")):
            with self.assertRaisesRegex(RuntimeError, "failed"):
                replace_aggregate_scope(db, "app_team_season_stats", "E", "E2025")
        self.assertEqual((db.commits, db.rollbacks), (0, 1))

    def test_quality_detects_missing_table_keys_and_values(self):
        name = "app_team_season_stats"
        db = Connection()
        with db.cursor() as cursor:
            db.exists = False
            self.assertEqual(check_aggregate_scope(cursor, name, "E", "E2025"),
                             [f"gold.{physical_name(name)} is missing"])
            db.exists = True
            expected = row(name)
            with patch("gold_etl.quality.read_aggregate_rows", return_value=[expected]), \
                    patch("gold_etl.quality._dict_rows", return_value=[]):
                self.assertIn("keys differ", check_aggregate_scope(cursor, name,
                                                                     "E", "E2025")[0])
            changed = {**expected, "own_points": 9}
            with patch("gold_etl.quality.read_aggregate_rows", return_value=[expected]), \
                    patch("gold_etl.quality._dict_rows", return_value=[changed]):
                self.assertIn("values differ", check_aggregate_scope(cursor, name,
                                                                       "E", "E2025")[0])
            with patch("gold_etl.quality.read_aggregate_rows", return_value=[expected]), \
                    patch("gold_etl.quality._dict_rows", return_value=[expected]):
                self.assertEqual(check_aggregate_scope(cursor, name, "E", "E2025"), [])

    def test_quality_detects_coverage_json_item_drift(self):
        name = "app_coverage_games"
        expected = row(name)
        expected["items"] = [{"key": "boxScores", "availableCount": 1}]
        changed = {**expected, "items": [{"key": "boxScores", "availableCount": 0}]}
        db = Connection()
        with db.cursor() as cursor, \
                patch("gold_etl.quality.read_aggregate_rows", return_value=[expected]), \
                patch("gold_etl.quality._dict_rows", return_value=[changed]):
            self.assertIn("values differ", check_aggregate_scope(cursor, name,
                                                                   "E", "E2025")[0])


if __name__ == "__main__":
    unittest.main()
