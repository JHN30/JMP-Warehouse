"""Home/away splits and last-N windows: hand-worked examples, storage, and consistency."""

import unittest
from decimal import Decimal
from unittest.mock import patch

from gold_etl.schema import columns
from gold_etl.team_rounds import derive_rows as stats_rows
from gold_etl.team_splits import derive_rows


def season(results):
    """results: (round, local, road, local points, road points[, phase])."""
    games, stats, advanced = [], [], []
    for code, (round_number, local, road, points, against, *phase) in enumerate(results, 1):
        games.append({"game_code": code, "phase_code": phase[0] if phase else "RS",
                      "round_number": round_number, "played": True,
                      "local_club_code": local, "road_club_code": road,
                      "local_club_name": local, "road_club_name": road,
                      "match_winner_club_code": local if points > against else road})
        for side, value in (("local", points), ("road", against)):
            stats.append({"game_code": code, "side": side, "stats_kind": "total",
                          "points": value})
            advanced.append({"game_code": code, "side": side, "possessions": Decimal(100),
                             "game_minutes": Decimal(40)})
    return games, stats, advanced


def derive(results):
    return derive_rows(*season(results))


def pick(rows, scope, round_number, club):
    return next(row for row in rows if (row["scope"], row["round_number"], row["club_code"])
                == (scope, round_number, club))


BASIC = [(1, "A", "B", 100, 90), (2, "C", "A", 85, 80), (3, "A", "D", 95, 90)]


class HomeAwayTests(unittest.TestCase):
    def test_rows_match_team_round_stats_and_registered_columns(self):
        games, stats, advanced = season(BASIC + [(4, "A", "B", 80, 70, "PO")])
        rows = derive_rows(games, stats, advanced)
        expected = stats_rows(games, stats, advanced, [])
        self.assertEqual([(r["scope"], r["round_number"], r["club_code"]) for r in rows],
                         [(r["scope"], r["round_number"], r["club_code"]) for r in expected])
        self.assertEqual(set(rows[0]) | {"competition_code", "season_code"},
                         set(columns("team_round_splits")))
        self.assertEqual({r["scope"] for r in rows}, {"all", "RS", "PO", "PS"})

    def test_home_and_away_values_from_the_local_and_road_sides(self):
        row = pick(derive(BASIC), "RS", 3, "A")
        self.assertEqual((row["home_games"], row["home_wins"]), (2, 2))
        self.assertEqual(row["home_mov"], Decimal("7.5"))            # (195 - 180) / 2
        self.assertEqual(row["home_offensive_rating"], Decimal("97.5"))
        self.assertEqual(row["home_defensive_rating"], Decimal("90"))
        self.assertEqual(row["home_net_rating"], Decimal("7.5"))
        self.assertEqual(row["home_pace"], Decimal("100"))
        self.assertEqual((row["away_games"], row["away_wins"]), (1, 0))
        self.assertEqual(row["away_mov"], Decimal("-5"))

    def test_group_without_games_has_zero_counts_and_null_rates(self):
        row = pick(derive(BASIC), "RS", 1, "B")
        self.assertEqual((row["home_games"], row["home_wins"]), (0, 0))
        self.assertIsNone(row["home_mov"])
        self.assertIsNone(row["home_pace"])
        self.assertEqual((row["away_games"], row["away_wins"]), (1, 0))

    def test_idle_rounds_carry_forward_and_late_clubs_have_no_earlier_rows(self):
        rows = derive(BASIC)
        b = [r for r in rows if r["scope"] == "RS" and r["club_code"] == "B"]
        self.assertEqual([r["round_number"] for r in b], [1, 2, 3])
        self.assertEqual(b[0]["away_mov"], b[2]["away_mov"])
        c = [r["round_number"] for r in rows if r["scope"] == "RS" and r["club_code"] == "C"]
        self.assertEqual(c, [2, 3])


class RollingTests(unittest.TestCase):
    RESULTS = [(r, "A", f"O{r}", 100 + r, 90) for r in range(1, 13)]

    def test_window_sizes_and_oldest_games_drop_out(self):
        rows = derive(self.RESULTS)
        three = pick(rows, "RS", 3, "A")
        self.assertEqual((three["last5_games"], three["last10_games"]), (3, 3))
        self.assertEqual(three["last5_mov"], Decimal("12"))           # margins 11, 12, 13
        ten = pick(rows, "RS", 10, "A")
        self.assertEqual((ten["last5_games"], ten["last10_games"]), (5, 10))
        self.assertEqual(ten["last10_mov"], pick(rows, "RS", 10, "A")["home_mov"])
        last = pick(rows, "RS", 12, "A")
        self.assertEqual(last["last5_mov"], Decimal("20"))            # rounds 8-12: 10 + r
        self.assertEqual(last["last10_mov"], Decimal("17.5"))         # rounds 3-12
        self.assertEqual(last["last5_wins"], 5)
        self.assertEqual(last["last5_offensive_rating"], Decimal("110"))   # 100 x 550 / 500
        self.assertEqual(last["last5_pace"], Decimal("100"))

    def test_two_games_in_one_round_use_game_code_order(self):
        results = [(r, "A", f"O{r}", 100, 90) for r in range(1, 5)]
        results += [(5, "A", "P", 50, 90), (5, "Q", "A", 70, 100)]
        row = pick(derive(results), "RS", 5, "A")
        self.assertEqual(row["last5_games"], 5)                       # oldest game dropped
        self.assertEqual(row["last5_mov"], Decimal("4"))              # (10 + 10 + 10 - 40 + 30) / 5
        self.assertEqual(row["last10_games"], 6)

    def test_idle_round_keeps_the_window(self):
        results = [(1, "A", "B", 100, 90), (2, "C", "D", 80, 70), (3, "C", "D", 80, 70)]
        rows = derive(results)
        self.assertEqual(pick(rows, "RS", 3, "A")["last5_mov"],
                         pick(rows, "RS", 1, "A")["last5_mov"])

    def test_missing_input_nulls_rates_but_keeps_counts(self):
        games, stats, advanced = season(BASIC)
        stats[0]["points"] = None
        row = pick(derive_rows(games, stats, advanced), "RS", 3, "A")
        self.assertIsNone(row["home_mov"])
        self.assertIsNone(row["last5_offensive_rating"])
        self.assertEqual(row["home_games"], 2)
        self.assertEqual(row["away_mov"], Decimal("-5"))              # away games are complete


class FakeCursor:
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


class FakeConnection:
    def __init__(self):
        self.queries, self.commits, self.rollbacks, self.exists = [], 0, 0, True

    def cursor(self):
        return FakeCursor(self)

    def __enter__(self):
        return self

    def __exit__(self, kind, *_):
        if kind:
            self.rollbacks += 1
        else:
            self.commits += 1
        return False


def stored_row():
    return dict(derive(BASIC)[0], competition_code="E", season_code="E2025")


class StorageTests(unittest.TestCase):
    def test_replace_is_scoped_atomic_and_rolls_back(self):
        from gold_etl.loader import replace_aggregate_scope

        db = FakeConnection()
        with patch("gold_etl.loader.read_aggregate_rows", return_value=[stored_row()]), \
                patch("psycopg2.extras.execute_values") as insert:
            self.assertEqual(replace_aggregate_scope(db, "team_round_splits", "E", "E2025"), 1)
        self.assertEqual((db.commits, db.rollbacks), (1, 0))
        self.assertTrue(any(query.startswith('DELETE FROM gold."app_team_round_splits"')
                            and params == ("E", "E2025") for query, params in db.queries))
        self.assertEqual(insert.call_args.args[2][0][:2], ("E", "E2025"))
        failing = FakeConnection()
        with patch("gold_etl.loader.read_aggregate_rows", return_value=[stored_row()]), \
                patch("psycopg2.extras.execute_values", side_effect=RuntimeError("failed")):
            with self.assertRaisesRegex(RuntimeError, "failed"):
                replace_aggregate_scope(failing, "team_round_splits", "E", "E2025")
        self.assertEqual((failing.commits, failing.rollbacks), (0, 1))

    def test_read_rows_uses_the_shared_silver_reader(self):
        from gold_etl import team_splits

        with patch.object(team_splits, "read_tables", return_value=season(BASIC) + ([],)):
            rows = team_splits.read_rows(object(), "E", "E2025")
        self.assertEqual(len(rows), len(derive(BASIC)))

    def test_quality_compares_a_fresh_derivation(self):
        from gold_etl.quality import check_aggregate_scope

        db, expected = FakeConnection(), stored_row()
        cursor = db.cursor()
        db.exists = False
        self.assertEqual(check_aggregate_scope(cursor, "team_round_splits", "E", "E2025"),
                         ["gold.app_team_round_splits is missing"])
        db.exists = True
        with patch("gold_etl.quality.read_aggregate_rows", return_value=[expected]):
            for actual, message in (([], "keys differ"),
                                    ([dict(expected, home_wins=9)], "values differ"),
                                    ([expected], None)):
                with patch("gold_etl.quality._dict_rows", return_value=actual):
                    issues = check_aggregate_scope(cursor, "team_round_splits", "E", "E2025")
                    self.assertEqual(issues == [], message is None)
                    if message:
                        self.assertIn(message, issues[0])


class ConsistencyTests(unittest.TestCase):
    def check(self, splits, stats):
        from gold_etl.quality import check_round_split_invariants

        with patch("gold_etl.quality._dict_rows", side_effect=[splits, stats]):
            return check_round_split_invariants(FakeConnection().cursor(), "E", "E2025")

    def data(self):
        games, stats_input, advanced = season(BASIC)
        splits = [r for r in derive_rows(games, stats_input, advanced) if r["scope"] == "RS"]
        stats = stats_rows(games, stats_input, advanced, [])
        return splits, [r for r in stats if r["scope"] == "RS"]

    def test_consistent_rows_pass(self):
        self.assertEqual(self.check(*self.data()), [])

    def test_games_wins_window_and_mov_mismatches_are_reported(self):
        splits, stats = self.data()
        bad = next(r for r in splits if r["round_number"] == 3 and r["club_code"] == "A")
        bad.update(home_games=5, home_wins=5, last5_games=1, last10_mov=Decimal("99"))
        issues = self.check(splits, stats)
        text = " | ".join(issues)
        for fragment in ("home + away games", "home + away wins", "last5_games",
                         "last10_mov differs"):
            self.assertIn(fragment, text)
        self.assertTrue(all("RS round 3 A" in issue for issue in issues))

    def test_missing_cumulative_row_is_reported(self):
        splits, stats = self.data()
        self.assertIn("no matching team_round_stats row", self.check(splits, stats[1:])[0])


if __name__ == "__main__":
    unittest.main()
