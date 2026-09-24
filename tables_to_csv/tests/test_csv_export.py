"""Pure selection and CLI checks; database export is verified separately."""

import unittest
from datetime import date

from tables_to_csv.main import build_parser
from tables_to_csv.utils import current_season_year, select_seasons


class CsvExportSelectionTests(unittest.TestCase):
    def test_cli_defaults_to_latest_database_season_and_all_tables(self):
        args = build_parser().parse_args([])
        self.assertEqual(args.competition, "euroleague")
        self.assertEqual(args.season_code, ["latest"])
        self.assertEqual(args.table, ["all"])

    def test_range_full_code_and_missing_seasons(self):
        seasons, missing = select_seasons(
            ["2023-2025", "E2025"], "euroleague", ["E2023", "E2025"]
        )
        self.assertEqual(seasons, ["E2023", "E2025"])
        self.assertEqual(missing, ["E2024"])

    def test_all_and_latest_use_database_availability(self):
        available = ["U2023", "U2025"]
        self.assertEqual(select_seasons(["all"], "eurocup", available),
                         (available, []))
        self.assertEqual(select_seasons(["latest"], "eurocup", available),
                         (["U2025"], []))

    def test_current_season_starts_in_september(self):
        self.assertEqual(current_season_year(date(2026, 8, 31)), 2025)
        self.assertEqual(current_season_year(date(2026, 9, 1)), 2026)

    def test_rejects_wrong_competition_or_descending_range(self):
        with self.assertRaisesRegex(ValueError, "Invalid season code"):
            select_seasons(["U2025"], "euroleague", ["E2025"])
        with self.assertRaisesRegex(ValueError, "range must ascend"):
            select_seasons(["2025-2023"], "euroleague", ["E2025"])

    def test_rejects_unavailable_explicit_season(self):
        with self.assertRaisesRegex(ValueError, "No requested euroleague seasons"):
            select_seasons(["2024"], "euroleague", ["E2025"])


if __name__ == "__main__":
    unittest.main()
