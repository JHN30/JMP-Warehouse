"""Pure checks for the Neon publisher and pipeline; database behaviour is verified separately."""

import unittest
from datetime import date
from unittest import mock

from neon_publish.main import build_parser
from neon_publish.publish import APP_TABLES, shrink_problems
from pipeline import season_code_for
from postgres_etl.flat_schema import TABLES


class PublishTests(unittest.TestCase):
    def test_app_tables_are_the_former_neon_import_set(self):
        self.assertEqual(len(APP_TABLES), 21)
        self.assertTrue(set(APP_TABLES) <= set(TABLES))
        self.assertNotIn("play_by_play", APP_TABLES)
        self.assertNotIn("source_payloads", APP_TABLES)

    def test_growth_and_small_changes_are_allowed(self):
        self.assertEqual(shrink_problems({"games": 380, "people": 95},
                                         {"games": 380, "people": 100}), [])
        self.assertEqual(shrink_problems({"games": 380}, {"games": None}), [])
        self.assertEqual(shrink_problems({"standings_basicstandings": 20},
                                         {"standings_basicstandings": 0}), [])

    def test_emptying_or_large_shrink_is_refused(self):
        problems = shrink_problems({"games": 0, "people": 80},
                                   {"games": 380, "people": 100})
        self.assertEqual(len(problems), 2)
        self.assertIn("etl_flat_games: 380 -> 0 rows", problems[0])

    def test_cli_defaults_to_current_season_and_all_app_tables(self):
        args = build_parser().parse_args([])
        self.assertEqual(args.season_code, ["current"])
        self.assertEqual(args.table, ["all"])
        self.assertFalse(args.allow_shrink)


class PipelineTests(unittest.TestCase):
    def test_season_code_tokens(self):
        self.assertEqual(season_code_for("euroleague", "2026"), "E2026")
        self.assertEqual(season_code_for("euroleague", "e2025"), "E2025")
        self.assertEqual(season_code_for("eurocup", "2024"), "U2024")
        with mock.patch("pipeline.current_season_year", return_value=2026):
            self.assertEqual(season_code_for("euroleague", "current"), "E2026")
        with self.assertRaises(ValueError):
            season_code_for("euroleague", "U2025")

    def test_current_season_rollover_is_september(self):
        from tables_to_csv.utils import current_season_year
        self.assertEqual(current_season_year(date(2026, 9, 24)), 2026)


if __name__ == "__main__":
    unittest.main()
