"""Physical Gold names: identical in Neon, Silver names preserved, indexes created."""

import unittest

from gold_etl.schema import (GOLD_TABLES, PHYSICAL_TABLES, create_table_sql,
                             count_sql, physical_name)
from neon_publish.contract import APP_TABLES, target_name
from neon_publish.publish import _relation


class NameTests(unittest.TestCase):
    def test_every_gold_table_uses_the_same_name_in_neon(self):
        self.assertEqual(set(APP_TABLES), set(PHYSICAL_TABLES))
        self.assertEqual(len(APP_TABLES), 40)
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

    def test_secondary_indexes_are_part_of_gold_creation(self):
        for name, columns in (("play_by_play", "game_code, play_number"),
                              ("shots", "person_code"), ("app_standings", "club_code")):
            self.assertIn("CREATE INDEX IF NOT EXISTS", create_table_sql(name))
            self.assertIn(f"({columns})", create_table_sql(name))


if __name__ == "__main__":
    unittest.main()
