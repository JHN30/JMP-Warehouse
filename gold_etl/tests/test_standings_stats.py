"""Standings stats table: the join equals its three in-memory sources, and storage."""

import unittest
from unittest.mock import patch

from gold_etl.schema import GOLD_TABLES, STANDINGS_STATS_SOURCES, columns
from gold_etl.standings_stats import derive_rows
from gold_etl.team_ratings import derive_rows as rating_rows
from gold_etl.team_rounds import derive_rows as stats_rows
from gold_etl.team_splits import derive_rows as split_rows
from gold_etl.tests.test_team_splits import FakeConnection, season

RESULTS = [(1, "A", "B", 100, 90), (1, "C", "D", 80, 85), (2, "C", "A", 85, 80),
           (2, "B", "D", 70, 75), (3, "A", "D", 95, 90), (4, "A", "C", 90, 88, "PO"),
           (4, "E", "B", 82, 70, "PO")]
TABLES = season(RESULTS) + ([{"club_code": "A", "name": "Club A"}],)


def key(row):
    return (row["scope"], row["round_number"], row["club_code"])


class JoinTests(unittest.TestCase):
    def test_every_column_equals_its_source_row(self):
        rows = derive_rows(*TABLES)
        by_key = {key(row): row for row in rows}
        sources = {"team_round_stats": stats_rows, "team_round_ratings": rating_rows,
                   "team_round_splits": split_rows}
        for name, _, names in STANDINGS_STATS_SOURCES:
            source = sources[name](*TABLES)
            self.assertEqual({key(row) for row in source}, set(by_key), name)
            for row in source:
                for column in names:
                    self.assertEqual(by_key[key(row)][column], row[column], (name, column))

    def test_row_set_scopes_and_late_starting_clubs(self):
        rows = derive_rows(*TABLES)
        self.assertEqual({row["scope"] for row in rows}, {"all", "RS", "PO", "PS"})
        self.assertEqual({key(row) for row in rows}, {key(row) for row in stats_rows(*TABLES)})
        first_e = min(row["round_number"] for row in rows
                      if row["club_code"] == "E" and row["scope"] == "all")
        self.assertEqual(first_e, 4)                     # E has no rows before it plays
        self.assertEqual(rows, sorted(rows, key=key))

    def test_columns_match_the_registered_table_and_leave_out_raw_totals(self):
        row = derive_rows(*TABLES)[0]
        self.assertEqual(set(row), set(columns("app_standings_stats"))
                         - {"competition_code", "season_code"})
        for excluded in ("game_minutes", "pythagorean_exponent", "own_points", "opp_points",
                         "own_field_goals_made"):
            self.assertNotIn(excluded, row)
        self.assertIn("club_name", row)
        self.assertIn("last10_net_rating", row)
        self.assertIn("adj_net_rating", row)

    def test_registered_outside_the_published_tables(self):
        from gold_etl.schema import DERIVED_NAMES, ROUND_NAMES

        self.assertIn("app_standings_stats", ROUND_NAMES)
        self.assertNotIn("app_standings_stats", DERIVED_NAMES)
        self.assertIn("app_standings_stats", GOLD_TABLES)
        for name, _, _ in STANDINGS_STATS_SOURCES:
            self.assertNotIn(name, GOLD_TABLES)             # intermediate, never stored

    def test_a_source_row_without_a_base_row_is_an_error(self):
        with patch("gold_etl.standings_stats.DERIVATIONS", {
                "team_round_stats": lambda *a: stats_rows(*a)[1:],
                "team_round_ratings": rating_rows, "team_round_splits": split_rows}):
            with self.assertRaisesRegex(ValueError, "no team_round_stats row"):
                derive_rows(*TABLES)


def stored_row():
    return dict(derive_rows(*TABLES)[0], competition_code="E", season_code="E2025")


class StorageTests(unittest.TestCase):
    def test_replace_is_scoped_atomic_and_rolls_back(self):
        from gold_etl.loader import replace_aggregate_scope

        db = FakeConnection()
        with patch("gold_etl.loader.read_aggregate_rows", return_value=[stored_row()]), \
                patch("psycopg2.extras.execute_values") as insert:
            self.assertEqual(replace_aggregate_scope(db, "app_standings_stats", "E", "E2025"), 1)
        self.assertEqual((db.commits, db.rollbacks), (1, 0))
        self.assertTrue(any(query.startswith('DELETE FROM gold."app_standings_stats"')
                            and params == ("E", "E2025") for query, params in db.queries))
        self.assertEqual(insert.call_args.args[2][0][:2], ("E", "E2025"))
        failing = FakeConnection()
        with patch("gold_etl.loader.read_aggregate_rows", return_value=[stored_row()]), \
                patch("psycopg2.extras.execute_values", side_effect=RuntimeError("failed")):
            with self.assertRaisesRegex(RuntimeError, "failed"):
                replace_aggregate_scope(failing, "app_standings_stats", "E", "E2025")
        self.assertEqual((failing.commits, failing.rollbacks), (0, 1))

    def test_read_rows_dispatches_through_the_shared_silver_reader(self):
        from gold_etl import standings_stats
        from gold_etl.loader import read_aggregate_rows

        with patch.object(standings_stats, "read_tables", return_value=TABLES) as reader:
            rows = read_aggregate_rows(object(), "app_standings_stats", "E", "E2025")
        reader.assert_called_once()
        self.assertEqual(len(rows), len(derive_rows(*TABLES)))

    def test_quality_compares_a_fresh_derivation(self):
        from gold_etl.quality import check_aggregate_scope

        db, expected = FakeConnection(), stored_row()
        cursor = db.cursor()
        with patch("gold_etl.quality.read_aggregate_rows", return_value=[expected]):
            for actual, message in (([], "keys differ"),
                                    ([dict(expected, home_wins=99)], "values differ"),
                                    ([expected], None)):
                with patch("gold_etl.quality._dict_rows", return_value=actual):
                    issues = check_aggregate_scope(cursor, "app_standings_stats", "E", "E2025")
                    self.assertEqual(issues == [], message is None)
                    if message:
                        self.assertIn(message, issues[0])


if __name__ == "__main__":
    unittest.main()
