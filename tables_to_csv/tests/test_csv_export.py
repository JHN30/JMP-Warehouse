"""CSV export: CLI defaults, table selection, query building, discovery and the BOM file."""

import tempfile
import unittest
from datetime import date
from pathlib import Path

from tables_to_csv.main import build_parser, select_tables
from tables_to_csv.utils import (
    BOM, LAYERS, copy_query, count_query, current_season_year, discover_tables, export_table,
    select_seasons,
)

SPEC = {"columns": [("competition_code", "text"), ("season_code", "text"),
                    ("game_code", "integer"), ("started", "boolean"), ("name", "text")],
        "key": ["competition_code", "season_code", "game_code"]}
NO_SEASON = {"columns": [("competition_code", "text"), ("value", "integer")], "key": []}
OTHER = {"columns": [("id", "integer")], "key": ["id"]}


class CliTests(unittest.TestCase):
    def test_defaults_export_every_table_and_season(self):
        args = build_parser().parse_args([])
        self.assertEqual((args.competition, args.season_code, args.table, args.layer),
                         ("euroleague", ["all"], ["all"], "all"))
        self.assertFalse(args.dry_run)
        self.assertEqual(LAYERS, ("silver", "gold"))

    def test_select_tables_by_name_across_layers_and_unknown_names(self):
        found = {("gold", "games"): SPEC, ("silver", "games"): SPEC, ("silver", "clubs"): OTHER}
        self.assertEqual(select_tables(found, ["all"]), found)
        self.assertEqual(list(select_tables(found, ["games"])),
                         [("gold", "games"), ("silver", "games")])
        with self.assertRaisesRegex(ValueError, "not found in the selected layers: nope"):
            select_tables(found, ["games", "nope"])


class QueryTests(unittest.TestCase):
    def test_copy_query_filters_competition_and_seasons_orders_by_key_and_casts_booleans(self):
        query = copy_query("silver", "games", SPEC, "euroleague", ["E2024", "E2025"])
        self.assertEqual(query, (
            'COPY (SELECT "competition_code", "season_code", "game_code", '
            '"started"::integer AS "started", "name" FROM "silver"."games" '
            "WHERE \"competition_code\" = 'E' AND \"season_code\" IN ('E2024', 'E2025') "
            'ORDER BY "competition_code", "season_code", "game_code") '
            "TO STDOUT WITH (FORMAT CSV, HEADER TRUE, ENCODING 'UTF8')"))

    def test_all_seasons_have_no_season_filter_and_tables_without_columns_are_unfiltered(self):
        query = copy_query("gold", "games", SPEC, "euroleague", None)
        self.assertNotIn("season_code\" IN", query)
        self.assertIn("\"competition_code\" = 'E'", query)
        bare = copy_query("gold", "x", OTHER, "euroleague", ["E2025"])
        self.assertNotIn("WHERE", bare)
        self.assertEqual(count_query("gold", "x", OTHER, "euroleague", None),
                         'SELECT count(*) FROM "gold"."x"')

    def test_tables_without_a_key_are_not_ordered_and_a_season_column_is_optional(self):
        query = copy_query("silver", "v", NO_SEASON, "eurocup", ["E2025"])
        self.assertNotIn("ORDER BY", query)
        self.assertIn("\"competition_code\" = 'U'", query)
        self.assertNotIn("season_code", query)

    def test_names_and_values_are_quoted(self):
        spec = {"columns": [("we\"ird", "text")], "key": ["we\"ird"]}
        self.assertIn('"we""ird"', copy_query("silver", "t\"x", spec, "euroleague", None))
        odd = {"columns": [("season_code", "text")], "key": []}
        self.assertIn("IN ('a''b')", copy_query("silver", "t", odd, "euroleague", ["a'b"]))


class DiscoveryTests(unittest.TestCase):
    def test_columns_and_primary_keys_are_grouped_per_table(self):
        answers = [
            [("silver", "games", "game_code", "integer"), ("silver", "games", "started",
                                                            "boolean"),
             ("gold", "clubs", "code", "text")],
            [("silver", "games", "game_code"), ("gold", "orphan", "x")],
        ]

        class Cursor:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def execute(self, query, params=None):
                self.params = params

            def fetchall(self):
                return answers.pop(0)

        class Connection:
            def cursor(self):
                return Cursor()

        found = discover_tables(Connection(), LAYERS)
        self.assertEqual(list(found), [("gold", "clubs"), ("silver", "games")])
        self.assertEqual(found[("silver", "games")],
                         {"columns": [("game_code", "integer"), ("started", "boolean")],
                          "key": ["game_code"]})
        self.assertEqual(found[("gold", "clubs")]["key"], [])


class ExportTests(unittest.TestCase):
    def test_the_file_starts_with_a_byte_order_mark_and_replaces_atomically(self):
        class Cursor:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def copy_expert(self, query, output):
                self.query = query
                output.write(b"a,b\n1,2\n")

        class Connection:
            def cursor(self):
                return Cursor()

        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / "csv_export" / "euroleague" / "silver" / "games.csv"
            export_table(Connection(), "silver", "games", SPEC, "euroleague", None, destination)
            self.assertEqual(destination.read_bytes(), BOM + b"a,b\n1,2\n")
            self.assertEqual([p.name for p in destination.parent.iterdir()], ["games.csv"])

    def test_a_failed_copy_leaves_no_file_and_keeps_the_old_one(self):
        class Cursor:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def copy_expert(self, query, output):
                raise RuntimeError("copy failed")

        class Connection:
            def cursor(self):
                return Cursor()

        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / "games.csv"
            destination.write_bytes(b"old")
            with self.assertRaisesRegex(RuntimeError, "copy failed"):
                export_table(Connection(), "silver", "games", SPEC, "euroleague", None,
                             destination)
            self.assertEqual(destination.read_bytes(), b"old")
            self.assertEqual([p.name for p in Path(folder).iterdir()], ["games.csv"])


class SeasonTests(unittest.TestCase):
    def test_range_full_code_and_missing_seasons(self):
        seasons, missing = select_seasons(["2023-2025", "E2025"], "euroleague",
                                          ["E2023", "E2025"])
        self.assertEqual(seasons, ["E2023", "E2025"])
        self.assertEqual(missing, ["E2024"])

    def test_current_season_starts_in_september(self):
        self.assertEqual(current_season_year(date(2026, 8, 31)), 2025)
        self.assertEqual(current_season_year(date(2026, 9, 1)), 2026)

    def test_rejects_wrong_competition_descending_range_and_unavailable_season(self):
        with self.assertRaisesRegex(ValueError, "Invalid season code"):
            select_seasons(["U2025"], "euroleague", ["E2025"])
        with self.assertRaisesRegex(ValueError, "range must ascend"):
            select_seasons(["2025-2023"], "euroleague", ["E2025"])
        with self.assertRaisesRegex(ValueError, "No requested euroleague seasons"):
            select_seasons(["2024"], "euroleague", ["E2025"])


if __name__ == "__main__":
    unittest.main()
