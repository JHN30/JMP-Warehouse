"""League-relative, SRS/SOS/SOV and adjusted ratings: hand-solved examples and storage."""

import unittest
from decimal import Decimal
from unittest.mock import patch

from gold_etl.schema import columns
from gold_etl.team_ratings import _solve, derive_rows
from gold_etl.team_rounds import derive_rows as stats_rows


def game(code, round_number, local, road, winner, phase="RS"):
    return {"game_code": code, "phase_code": phase, "round_number": round_number,
            "played": True, "local_club_code": local, "road_club_code": road,
            "local_club_name": local, "road_club_name": road,
            "match_winner_club_code": winner}


def season(results, possessions=100):
    """results: (round, local, road, local points, road points[, phase])."""
    games, stats, advanced = [], [], []
    for code, (round_number, local, road, points, against, *phase) in enumerate(results, 1):
        winner = local if points > against else road
        games.append(game(code, round_number, local, road, winner, *phase))
        for side, value in (("local", points), ("road", against)):
            stats.append({"game_code": code, "side": side, "stats_kind": "total",
                          "points": value})
            advanced.append({"game_code": code, "side": side,
                             "possessions": Decimal(possessions),
                             "game_minutes": Decimal(40)})
    return games, stats, advanced


def derive(results, **kwargs):
    return derive_rows(*season(results, **kwargs))


def pick(rows, scope, round_number, club):
    return next(row for row in rows if (row["scope"], row["round_number"], row["club_code"])
                == (scope, round_number, club))


THREE = [(1, "A", "B", 100, 90), (2, "B", "C", 95, 85), (3, "A", "C", 90, 80)]


class SolverTests(unittest.TestCase):
    def test_solves_a_linear_system_and_rejects_a_singular_one(self):
        self.assertEqual([round(x, 9) for x in _solve([[2, 1], [1, 3]], [3, 5])], [0.8, 1.4])
        with self.assertRaises(ValueError):
            _solve([[1, 1], [1, 1]], [1, 2])


class RelativeTests(unittest.TestCase):
    def test_rows_match_team_round_stats_keys(self):
        games, stats, advanced = season(THREE + [(4, "A", "B", 80, 70, "PO")])
        rows = derive_rows(games, stats, advanced)
        expected = stats_rows(games, stats, advanced, [])
        self.assertEqual([(r["scope"], r["round_number"], r["club_code"]) for r in rows],
                         [(r["scope"], r["round_number"], r["club_code"]) for r in expected])
        self.assertEqual(set(rows[0]) | {"competition_code", "season_code"},
                         set(columns("team_round_ratings")))
        self.assertEqual({r["scope"] for r in rows}, {"all", "RS", "PO", "PS"})

    def test_league_and_relative_values(self):
        row = pick(derive(THREE), "RS", 3, "A")
        self.assertEqual(row["league_offensive_rating"], Decimal("90"))   # 540 / 600
        self.assertEqual(row["league_pace"], Decimal("100"))              # 40 x 200 / 80
        self.assertEqual(row["relative_offensive_rating"], Decimal("5"))  # 95 - 90
        self.assertEqual(row["relative_defensive_rating"], Decimal("-5"))  # 85 - 90
        self.assertEqual(row["relative_pace"], Decimal("0"))

    def test_idle_club_carries_forward_with_current_league(self):
        rows = derive(THREE)
        self.assertEqual([(r["round_number"], r["connected"]) for r in rows
                          if r["scope"] == "RS" and r["club_code"] == "A"],
                         [(1, True), (2, True), (3, True)])
        self.assertEqual(pick(rows, "RS", 2, "A")["league_offensive_rating"],
                         pick(rows, "RS", 2, "C")["league_offensive_rating"])
        self.assertEqual([r["round_number"] for r in rows
                          if r["scope"] == "RS" and r["club_code"] == "C"], [2, 3])


class SrsTests(unittest.TestCase):
    def test_three_club_example(self):
        rows = derive(THREE)
        a, b, c = (pick(rows, "RS", 3, club) for club in "ABC")
        self.assertTrue(a["connected"])
        self.assertAlmostEqual(float(a["srs"]), 20 / 3, places=5)
        self.assertAlmostEqual(float(b["srs"]), 0, places=5)
        self.assertAlmostEqual(float(c["srs"]), -20 / 3, places=5)
        self.assertAlmostEqual(float(a["sos"]), -10 / 3, places=5)     # srs - mov
        self.assertAlmostEqual(float(a["sov"]), -10 / 3, places=5)     # beat B and C
        self.assertAlmostEqual(float(b["sov"]), -20 / 3, places=5)     # beat C only
        self.assertIsNone(c["sov"])                                    # no wins

    def test_sum_zero_and_sos_identity_across_rounds(self):
        rows = derive(THREE + [(4, "B", "A", 88, 84), (5, "C", "B", 70, 92)])
        for number in (2, 3, 4, 5):
            connected = [r for r in rows if r["scope"] == "RS" and r["round_number"] == number]
            self.assertAlmostEqual(sum(float(r["srs"]) for r in connected), 0, places=5)

    def test_sos_equals_srs_minus_mov(self):
        games, stats, advanced = season(THREE + [(4, "B", "A", 88, 84)])
        rows = derive_rows(games, stats, advanced)
        totals = {r["club_code"]: r for r in stats_rows(games, stats, advanced, [])
                  if r["scope"] == "RS" and r["round_number"] == 4}
        for club in "ABC":
            row = pick(rows, "RS", 4, club)
            self.assertAlmostEqual(float(row["sos"]), float(row["srs"]) - float(totals[club]["mov"]),
                                   places=5)

    def test_disconnected_graph_and_single_game_ratings(self):
        rows = derive([(1, "A", "B", 100, 90), (1, "C", "D", 95, 85)])
        row = pick(rows, "RS", 1, "A")
        self.assertFalse(row["connected"])
        for column in ("srs", "sos", "sov", "adj_offensive_rating", "adj_defensive_rating",
                       "adj_net_rating"):
            self.assertIsNone(row[column], column)
        self.assertIsNotNone(row["league_offensive_rating"])       # never depends on connectivity
        single = pick(derive([(1, "A", "B", 100, 90)]), "RS", 1, "A")
        self.assertTrue(single["connected"])
        self.assertAlmostEqual(float(single["srs"]), 5, places=5)

    def test_missing_input_nulls_every_rating_for_the_scope_round(self):
        games, stats, advanced = season(THREE)
        stats[0]["points"] = None
        row = pick(derive_rows(games, stats, advanced), "RS", 3, "A")
        self.assertFalse(row["connected"])
        self.assertIsNone(row["league_offensive_rating"])
        self.assertIsNone(row["srs"])


class AdjustedTests(unittest.TestCase):
    def test_three_club_example(self):
        rows = derive(THREE)
        a, b, c = (pick(rows, "RS", 3, club) for club in "ABC")
        self.assertAlmostEqual(float(a["adj_net_rating"]), 20 / 3, places=5)
        self.assertAlmostEqual(float(a["adj_offensive_rating"]), (180 + 20 / 3) / 2, places=5)
        self.assertAlmostEqual(float(a["adj_defensive_rating"]), (180 - 20 / 3) / 2, places=5)
        self.assertAlmostEqual(float(b["adj_offensive_rating"]), 95, places=5)
        self.assertAlmostEqual(float(c["adj_offensive_rating"]), (170 - 20 / 3) / 2, places=5)
        for row in (a, b, c):
            self.assertAlmostEqual(float(row["adj_offensive_rating"] - row["adj_defensive_rating"]),
                                   float(row["adj_net_rating"]), places=5)

    def test_bipartite_graph_keeps_net_but_not_offense_and_defense(self):
        rows = derive([(1, "A", "B", 100, 90)])
        a, b = pick(rows, "RS", 1, "A"), pick(rows, "RS", 1, "B")
        self.assertAlmostEqual(float(a["adj_net_rating"]), 5, places=5)
        self.assertAlmostEqual(float(b["adj_net_rating"]), -5, places=5)
        for column in ("adj_offensive_rating", "adj_defensive_rating"):
            self.assertIsNone(a[column])
        self.assertTrue(a["connected"])
        self.assertIsNotNone(a["srs"])

    def test_possession_weighted_means_match_the_league(self):
        results = THREE + [(4, "B", "A", 88, 84), (5, "C", "B", 70, 92)]
        rows = derive(results)
        for number in (3, 4, 5):
            group = [r for r in rows if r["scope"] == "RS" and r["round_number"] == number]
            # Equal possessions per game, so a club's weight is its number of games.
            games = {}
            for _, local, road, *_ in results[:number]:
                games[local] = games.get(local, 0) + 1
                games[road] = games.get(road, 0) + 1
            weight = sum(games[r["club_code"]] for r in group)
            league = float(group[0]["league_offensive_rating"])
            for column, expected in (("adj_offensive_rating", league),
                                     ("adj_defensive_rating", league),
                                     ("adj_net_rating", 0.0)):
                if group[0][column] is None:
                    continue
                mean = sum(games[r["club_code"]] * float(r[column]) for r in group) / weight
                self.assertAlmostEqual(mean, expected, places=4, msg=column)


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
    return dict(derive(THREE)[0], competition_code="E", season_code="E2025")


class StorageTests(unittest.TestCase):
    def test_replace_is_scoped_and_atomic_and_rolls_back(self):
        from gold_etl.loader import replace_aggregate_scope

        db = FakeConnection()
        with patch("gold_etl.loader.read_aggregate_rows", return_value=[stored_row()]), \
                patch("psycopg2.extras.execute_values") as insert:
            self.assertEqual(replace_aggregate_scope(db, "team_round_ratings", "E", "E2025"), 1)
        self.assertEqual((db.commits, db.rollbacks), (1, 0))
        self.assertTrue(any(query.startswith('DELETE FROM gold."app_team_round_ratings"')
                            and params == ("E", "E2025") for query, params in db.queries))
        self.assertEqual(insert.call_args.args[2][0][:2], ("E", "E2025"))
        failing = FakeConnection()
        with patch("gold_etl.loader.read_aggregate_rows", return_value=[stored_row()]), \
                patch("psycopg2.extras.execute_values", side_effect=RuntimeError("failed")):
            with self.assertRaisesRegex(RuntimeError, "failed"):
                replace_aggregate_scope(failing, "team_round_ratings", "E", "E2025")
        self.assertEqual((failing.commits, failing.rollbacks), (0, 1))

    def test_read_rows_uses_the_shared_silver_reader(self):
        from gold_etl import team_ratings

        with patch.object(team_ratings, "read_tables", return_value=season(THREE) + ([],)):
            rows = team_ratings.read_rows(object(), "E", "E2025")
        self.assertEqual(len(rows), len(derive(THREE)))

    def test_quality_compares_a_fresh_derivation(self):
        from gold_etl.quality import check_aggregate_scope

        db, expected = FakeConnection(), stored_row()
        cursor = db.cursor()
        db.exists = False
        self.assertEqual(check_aggregate_scope(cursor, "team_round_ratings", "E", "E2025"),
                         ["gold.app_team_round_ratings is missing"])
        db.exists = True
        with patch("gold_etl.quality.read_aggregate_rows", return_value=[expected]):
            for actual, message in (([], "keys differ"),
                                    ([dict(expected, srs=Decimal(9))], "values differ"),
                                    ([expected], None)):
                with patch("gold_etl.quality._dict_rows", return_value=actual):
                    issues = check_aggregate_scope(cursor, "team_round_ratings", "E", "E2025")
                    self.assertEqual(issues == [], message is None)
                    if message:
                        self.assertIn(message, issues[0])


class InvariantTests(unittest.TestCase):
    def check(self, ratings, stats):
        from gold_etl.quality import check_round_rating_invariants

        with patch("gold_etl.quality._dict_rows", side_effect=[ratings, stats]):
            return check_round_rating_invariants(FakeConnection().cursor(), "E", "E2025")

    def rows(self, **changes):
        ratings = [dict(scope="RS", round_number=3, club_code=club, connected=True,
                        srs=Decimal(value), adj_net_rating=Decimal(value))
                   for club, value in (("A", 5), ("B", 0), ("C", -5))]
        for row in ratings:
            row.update(changes)
        stats = [dict(scope="RS", round_number=3, club_code=club, possessions=Decimal(200))
                 for club in "ABC"]
        return ratings, stats

    def test_balanced_ratings_pass(self):
        self.assertEqual(self.check(*self.rows()), [])

    def test_unbalanced_sums_are_reported(self):
        ratings, stats = self.rows()
        ratings[0]["srs"] = Decimal(7)
        ratings[0]["adj_net_rating"] = Decimal(7)
        issues = self.check(ratings, stats)
        self.assertEqual(len(issues), 2)
        self.assertTrue(any("srs" in issue and "RS round 3" in issue for issue in issues))

    def test_disconnected_scope_rounds_are_skipped(self):
        ratings, stats = self.rows(connected=False, srs=None, adj_net_rating=None)
        self.assertEqual(self.check(ratings, stats), [])


if __name__ == "__main__":
    unittest.main()
