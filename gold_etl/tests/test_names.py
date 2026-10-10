"""Physical names and safe, repeatable local migration planning."""

import unittest
from unittest.mock import MagicMock

from gold_etl.migrate_names import migrate, rename_plan
from gold_etl.schema import (GOLD_TABLES, PHYSICAL_TABLES, create_table_sql,
                             count_sql, physical_name)
from neon_publish.contract import APP_TABLES, target_name
from neon_publish.publish import _relation


class NameTests(unittest.TestCase):
    def test_every_gold_table_uses_the_same_name_in_neon(self):
        self.assertEqual(set(APP_TABLES), set(PHYSICAL_TABLES))
        self.assertEqual(len(APP_TABLES), 47)
        for name in GOLD_TABLES:
            target = physical_name(name)
            self.assertTrue(target.startswith("app_"))
            self.assertEqual(target_name(target), target)
            self.assertIn(f'gold."{target}"', create_table_sql(name))
            self.assertIn(f'gold."{target}"', count_sql(name, "gold"))
            self.assertEqual(_relation(target, "gold").strings, ("gold", target))
            self.assertEqual(_relation(target, "public").strings, ("public", target))

    def test_silver_source_names_are_preserved(self):
        self.assertIn('silver."games"', count_sql("games", "silver"))
        self.assertNotIn('silver."app_games"', count_sql("games", "silver"))

    def test_legacy_database_renames_exactly_36_tables(self):
        plan = rename_plan(set(GOLD_TABLES))
        self.assertEqual(len(plan), 36)
        self.assertIn(("games", "app_games"), plan)
        self.assertFalse(any(source.startswith("app_") for source, _ in plan))

    def test_already_migrated_database_is_idempotent(self):
        self.assertEqual(rename_plan(set(PHYSICAL_TABLES)), [])

    def test_collision_missing_and_unexpected_tables_are_refused(self):
        for existing in (set(GOLD_TABLES) | {"app_games"},
                         set(GOLD_TABLES) - {"games"},
                         set(GOLD_TABLES) | {"unknown"}):
            with self.subTest(existing=existing), self.assertRaises(ValueError):
                rename_plan(existing)

    def test_preview_does_not_mutate_and_apply_rolls_back_on_failure(self):
        db = MagicMock()
        cursor = db.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = [(name,) for name in GOLD_TABLES]
        self.assertEqual(len(migrate(db)), 36)
        self.assertEqual(cursor.execute.call_count, 2)
        cursor.execute.reset_mock()
        cursor.execute.side_effect = [None, None, RuntimeError("rename failed")]
        with self.assertRaisesRegex(RuntimeError, "rename failed"):
            migrate(db, apply=True)
        self.assertEqual(db.__exit__.call_args.args[0], RuntimeError)

    def test_secondary_indexes_are_part_of_gold_creation(self):
        for name, columns in (("play_by_play", "game_code, play_number"),
                              ("shots", "person_code"), ("app_standings", "club_code")):
            self.assertIn("CREATE INDEX IF NOT EXISTS", create_table_sql(name))
            self.assertIn(f"({columns})", create_table_sql(name))


if __name__ == "__main__":
    unittest.main()
