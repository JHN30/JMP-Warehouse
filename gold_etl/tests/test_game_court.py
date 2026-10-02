"""On-court intervals, lineup stints and stat gaps copied from Silver into Gold (feature 30j)."""

import unittest

from gold_etl.loader import replace_scope
from gold_etl.quality import check_scope
from gold_etl.schema import (COPIED_TABLES, GAME_COURT_NAMES, GOLD_TABLES, SOURCE_NAMES, TABLES,
                             columns, count_sql, create_table_sql)
from gold_etl.tests.test_gold import FakeConnection
from postgres_etl.flat_schema import ALL_TABLES as SILVER_TABLES

KEYS = {
    "game_player_on_court": ("competition_code", "season_code", "game_code", "side",
                             "person_key", "interval_ordinal"),
    "game_team_lineup_stints": ("competition_code", "season_code", "game_code", "side",
                                "stint_ordinal"),
    "game_stat_gaps": ("competition_code", "season_code", "game_code", "stat_name"),
}


class SchemaTests(unittest.TestCase):
    def test_tables_copy_the_silver_fields_without_provenance(self):
        self.assertEqual(len(GAME_COURT_NAMES), 3)
        for name in GAME_COURT_NAMES:
            self.assertEqual(columns(name),
                             tuple(field.name for field in SILVER_TABLES[name].fields))
            self.assertNotIn("load_id", columns(name))
            self.assertNotIn("loaded_at", columns(name))
            self.assertEqual(GOLD_TABLES[name].key, KEYS[name])
            self.assertIn(f'gold."{name}"', create_table_sql(name))
            self.assertIn(f'gold."{name}"', count_sql(name, "gold"))

    def test_source_projections_stay_sixteen_and_names_are_unique(self):
        self.assertEqual((len(SOURCE_NAMES), len(TABLES)), (16, 16))
        self.assertFalse(set(GAME_COURT_NAMES) & set(SOURCE_NAMES))
        self.assertTrue(set(GAME_COURT_NAMES) <= set(COPIED_TABLES))

    def test_known_columns(self):
        self.assertEqual(columns("game_player_on_court")[-3:],
                         ("club_code", "start_seconds", "end_seconds"))
        self.assertIn("opponent_players", columns("game_team_lineup_stints"))
        self.assertEqual(columns("game_stat_gaps")[-1], "reason")


class LoaderTests(unittest.TestCase):
    def test_copy_is_scoped_explicit_and_one_transaction(self):
        for name in GAME_COURT_NAMES:
            db = FakeConnection()
            self.assertEqual(replace_scope(db, name, "E", "E2025"), 2)
            self.assertEqual((db.commits, db.rollbacks), (1, 0))
            sql = [query for query, _ in db.statements]
            self.assertTrue(sql[2].startswith(f'DELETE FROM gold."{name}"'))
            self.assertTrue(sql[3].startswith(f'INSERT INTO gold."{name}"'))
            self.assertIn(f'FROM silver."{name}"', sql[3])
            self.assertNotIn("load_id", sql[3])
            self.assertEqual(db.statements[3][1], ("E", "E2025"))

    def test_an_empty_source_clears_the_scope(self):
        db = FakeConnection(source_count=0)
        self.assertEqual(replace_scope(db, "game_stat_gaps", "E", "E2025"), 0)
        self.assertEqual(db.commits, 1)

    def test_failed_insert_rolls_back(self):
        db = FakeConnection()
        db.fail_insert = True
        with self.assertRaisesRegex(RuntimeError, "insert failed"):
            replace_scope(db, "game_team_lineup_stints", "E", "E2025")
        self.assertEqual((db.commits, db.rollbacks), (0, 1))

    def test_unknown_tables_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unknown Gold source table"):
            replace_scope(FakeConnection(), "game_team_unknown", "E", "E2025")
        with self.assertRaisesRegex(ValueError, "Unknown Gold source table"):
            check_scope(FakeConnection().cursor(), "game_team_unknown", "E", "E2025")


if __name__ == "__main__":
    unittest.main()
