"""Cumulative player rows: scopes, appearances, formulas, storage, and the feature 25 tie."""

import sys
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from gold_etl.player_rounds import derive_rows
from gold_etl.schema import columns

BASE = dict(seconds_played=0, points=0, field_goals_made=0, field_goals_attempted=0,
            three_pointers_made=0, three_pointers_attempted=0, free_throws_made=0,
            free_throws_attempted=0, offensive_rebounds=0, defensive_rebounds=0,
            total_rebounds=0, assists=0, steals=0, turnovers=0, blocks=0,
            fouls_committed=0, pir=0)
LOCAL = dict(BASE, points=83, field_goals_made=30, field_goals_attempted=60,
             three_pointers_made=8, three_pointers_attempted=20, free_throws_made=15,
             free_throws_attempted=20, offensive_rebounds=10, defensive_rebounds=25,
             total_rebounds=35, assists=15, steals=6, turnovers=12, blocks=3,
             fouls_committed=18)
ROAD = dict(BASE, points=74, field_goals_made=28, field_goals_attempted=62,
            three_pointers_made=6, three_pointers_attempted=18, free_throws_made=12,
            free_throws_attempted=16, offensive_rebounds=9, defensive_rebounds=22,
            total_rebounds=31, assists=12, steals=5, turnovers=10, blocks=2,
            fouls_committed=20)
STAR = dict(BASE, seconds_played=1200, points=20, field_goals_made=8, field_goals_attempted=15,
            three_pointers_made=2, three_pointers_attempted=5, free_throws_made=2,
            free_throws_attempted=4, offensive_rebounds=2, defensive_rebounds=4,
            total_rebounds=6, assists=5, steals=2, turnovers=3, blocks=1,
            fouls_committed=2)


def minus(total, part):
    return {key: total[key] - part[key] for key in total}


def game(code, round_number, local="MAD", road="BAR", phase="RS"):
    return {"game_code": code, "phase_code": phase, "round_number": round_number,
            "played": True, "local_club_code": local, "road_club_code": road,
            "local_club_name": local, "road_club_name": road,
            "match_winner_club_code": local}


def box(code, local=LOCAL, road=ROAD, possessions="70.42", minutes=40):
    stats = [dict(local, game_code=code, side="local", stats_kind="total"),
             dict(road, game_code=code, side="road", stats_kind="total")]
    advanced = [{"game_code": code, "side": side, "possessions": Decimal(possessions),
                 "game_minutes": Decimal(minutes)} for side in ("local", "road")]
    return stats, advanced


def player(code, key, side="local", club="MAD", name=None, started=False, **stats):
    return dict(BASE, **stats, game_code=code, side=side, person_key=key, club_code=club,
                person_name=name or key, started=started)


def derive(games, boxes, players, scores=None):
    stats = [row for rows, _ in boxes for row in rows]
    advanced = [row for _, rows in boxes for row in rows]
    return derive_rows(games, stats, advanced, [], players, scores or [])


def pick(rows, scope, round_number, key):
    return next(row for row in rows if (row["scope"], row["round_number"], row["person_key"])
                == (scope, round_number, key))


def full_game(code=1, round_number=1, phase="RS"):
    bench = dict(minus(LOCAL, STAR), seconds_played=11800)
    players = [player(code, "P1", started=True, **STAR), player(code, "P2", **bench),
               player(code, "R1", side="road", club="BAR", **dict(ROAD, seconds_played=12000))]
    return [game(code, round_number, phase=phase)], [box(code)], players


class AppearanceTests(unittest.TestCase):
    def test_scopes_totals_and_registered_columns(self):
        games, boxes, players = full_game()
        games += [game(2, 39, phase="PO")]
        boxes += [box(2)]
        players += [player(2, "P1", **STAR)]
        rows = derive(games, boxes, players)
        self.assertEqual({r["scope"] for r in rows}, {"all", "RS", "PO", "PS"})
        self.assertEqual(set(rows[0]) | {"competition_code", "season_code"},
                         set(columns("player_round_stats")))
        latest = pick(rows, "all", 39, "P1")
        self.assertEqual((latest["games_played"], latest["games_started"]), (2, 1))
        self.assertEqual(latest["points"], 40)
        self.assertEqual(latest["seconds_played"], 2400)
        self.assertEqual(pick(rows, "PS", 39, "P1")["games_played"], 1)

    def test_dnp_and_uncounted_games_are_not_appearances(self):
        games, boxes, players = full_game()
        players.append(player(1, "P3", seconds_played=0, points=0))
        games += [game(2, 2)]
        half = box(2)
        boxes += [(half[0][:1], half[1])]                        # one side has no totals
        players += [player(2, "P1", **STAR)]
        rows = derive(games, boxes, players)
        self.assertFalse([r for r in rows if r["person_key"] == "P3"])
        self.assertEqual({r["round_number"] for r in rows if r["person_key"] == "P1"}, {1})

    def test_idle_rounds_carry_forward_and_first_row_is_the_first_appearance(self):
        games, boxes, players = full_game()
        games += [game(2, 2, local="X", road="Y"), game(3, 3, local="X", road="Y")]
        boxes += [box(2), box(3)]
        players += [player(3, "P9", club="X", **STAR)]
        rows = derive(games, boxes, players)
        p1 = [r for r in rows if r["scope"] == "RS" and r["person_key"] == "P1"]
        self.assertEqual([r["round_number"] for r in p1], [1, 2, 3])
        self.assertEqual(p1[0]["ts_pct"], p1[2]["ts_pct"])
        self.assertEqual([r["round_number"] for r in rows
                          if r["scope"] == "RS" and r["person_key"] == "P9"], [3])

    def test_club_change_keeps_one_row_with_the_latest_club(self):
        games = [game(1, 1), game(2, 2, local="X", road="BAR")]
        boxes = [box(1), box(2)]
        players = [player(1, "P1", club="MAD", name="Old Name", **STAR),
                   player(2, "P1", club="X", name="New Name", **STAR)]
        rows = derive(games, boxes, players)
        latest = pick(rows, "RS", 2, "P1")
        self.assertEqual((latest["club_code"], latest["player_name"]), ("X", "New Name"))
        self.assertEqual(latest["games_played"], 2)
        self.assertEqual(len([r for r in rows if r["scope"] == "RS"
                              and r["round_number"] == 2 and r["person_key"] == "P1"]), 1)

    def test_missing_value_makes_totals_and_dependent_rates_null(self):
        games, boxes, players = full_game()
        players[0]["assists"] = None
        row = pick(derive(games, boxes, players), "RS", 1, "P1")
        self.assertIsNone(row["assists"])
        self.assertIsNone(row["ast_pct"])
        self.assertIsNone(row["assists_per_100"])
        self.assertEqual(row["points"], 20)
        self.assertIsNotNone(row["ts_pct"])


class FormulaTests(unittest.TestCase):
    def setUp(self):
        self.games, self.boxes, self.players = full_game()
        self.rows = derive(self.games, self.boxes, self.players,
                           [{"game_code": 1, "side": "local", "person_key": "P1",
                             "game_score": Decimal("16.9")}])

    def test_one_game_rates_for_the_star(self):
        row = pick(self.rows, "RS", 1, "P1")
        share = 1200 / 2400
        self.assertAlmostEqual(float(row["ts_pct"]), 20 / (2 * 16.76), places=5)
        self.assertEqual(row["efg_pct"], Decimal("0.600000"))
        self.assertAlmostEqual(float(row["usg_pct"]), (15 + 0.44 * 4 + 3) / (share * 80.8), places=4)
        self.assertAlmostEqual(float(row["ast_pct"]), 5 / (share * 30 - 8), places=4)
        self.assertAlmostEqual(float(row["orb_pct"]), 2 / (share * (10 + 22)), places=4)
        self.assertAlmostEqual(float(row["drb_pct"]), 4 / (share * (25 + 9)), places=4)
        self.assertAlmostEqual(float(row["trb_pct"]), 6 / (share * (35 + 31)), places=4)
        self.assertAlmostEqual(float(row["stl_pct"]), 2 / (share * 70.42), places=4)
        self.assertAlmostEqual(float(row["blk_pct"]), 1 / (share * (62 - 18)), places=4)
        self.assertAlmostEqual(float(row["tov_pct"]), 3 / (15 + 1.76 + 3), places=5)
        self.assertAlmostEqual(float(row["possessions_played"]), share * 70.42, places=5)
        self.assertAlmostEqual(float(row["points_per_100"]), 100 * 20 / (share * 70.42), places=3)
        self.assertEqual(row["game_score_total"], Decimal("16.9"))
        self.assertEqual(row["game_score_average"], Decimal("16.9"))

    def test_pie_across_all_players_of_a_game_sums_to_one(self):
        total = sum(pick(self.rows, "RS", 1, key)["pie"] for key in ("P1", "P2", "R1"))
        self.assertAlmostEqual(float(total), 1.0, places=4)

    def test_two_games_with_different_teams_use_sums_of_numerators_and_denominators(self):
        games = self.games + [game(2, 2, local="X", road="MAD")]
        other = dict(LOCAL, points=90, field_goals_attempted=70, free_throws_attempted=10)
        boxes = self.boxes + [box(2, local=other, road=LOCAL, possessions="80", minutes=45)]
        second = dict(STAR, seconds_played=1500)
        players = self.players + [player(2, "P1", side="road", club="MAD", **second)]
        row = pick(derive(games, boxes, players), "RS", 2, "P1")
        t1, t2 = 2400, 45 * 60
        share1, share2 = 1200 / t1, 1500 / t2
        used = 15 + 0.44 * 4 + 3
        self.assertAlmostEqual(float(row["usg_pct"]),
                               (used * t1 + used * t2) / (1200 * 80.8 + 1500 * 80.8), places=4)
        self.assertAlmostEqual(float(row["stl_pct"]),
                               4 / (share1 * 70.42 + share2 * 80), places=4)
        # In game 2 the opponent (X) attempted 70 field goals and 20 three-pointers.
        self.assertAlmostEqual(float(row["blk_pct"]),
                               2 / (share1 * (62 - 18) + share2 * (70 - 20)), places=4)
        self.assertAlmostEqual(float(row["ast_pct"]),
                               10 / (share1 * 30 - 8 + share2 * 30 - 8), places=4)

    def test_zero_denominators_are_null(self):
        games, boxes, players = full_game()
        players[0].update(field_goals_attempted=0, free_throws_attempted=0, turnovers=0)
        row = pick(derive(games, boxes, players), "RS", 1, "P1")
        self.assertIsNone(row["ts_pct"])
        self.assertIsNone(row["efg_pct"])
        self.assertIsNone(row["tov_pct"])

    def test_one_game_row_matches_feature_25_per_game_values(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "postgres_etl"))
        try:
            import advanced
        finally:
            sys.path.pop(0)
        games, boxes, players = full_game()
        stats = boxes[0][0]
        _, per_player = advanced.derive_rows(games, [], stats, players, [])
        scores = [{"game_code": r["game_code"], "side": r["side"], "person_key": r["person_key"],
                   "game_score": r["game_score"]} for r in per_player]
        rows = derive(games, boxes, players, scores)
        for expected in per_player:
            actual = pick(rows, "RS", 1, expected["person_key"])
            # Only the columns that do not depend on the minutes share are tied to feature 25:
            # its share is player seconds / (5 x game seconds) instead of 5 x seconds / (5 x game seconds),
            # so its usage, assist, rebound, steal and block rates are wrong (usage is 5x too large).
            for mine, theirs in (("ts_pct", "true_shooting_pct"), ("efg_pct", "efg_pct"),
                                 ("tov_pct", "tov_pct")):
                if expected[theirs] is None:
                    self.assertIsNone(actual[mine], (expected["person_key"], mine))
                    continue
                # Feature 25 divides by a minutes share already rounded to 6 places.
                self.assertAlmostEqual(float(actual[mine]), float(expected[theirs]),
                                       delta=1e-4, msg=(expected["person_key"], mine))
            self.assertEqual(actual["game_score_total"], expected["game_score"])


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
    games, boxes, players = full_game()
    return dict(derive(games, boxes, players)[0], competition_code="E", season_code="E2025")


class StorageTests(unittest.TestCase):
    def test_replace_is_scoped_atomic_and_rolls_back(self):
        from gold_etl.loader import replace_aggregate_scope

        db = FakeConnection()
        with patch("gold_etl.loader.read_aggregate_rows", return_value=[stored_row()]), \
                patch("psycopg2.extras.execute_values") as insert:
            self.assertEqual(replace_aggregate_scope(db, "player_round_stats", "E", "E2025"), 1)
        self.assertEqual((db.commits, db.rollbacks), (1, 0))
        self.assertTrue(any(query.startswith('DELETE FROM gold."app_player_round_stats"')
                            and params == ("E", "E2025") for query, params in db.queries))
        self.assertEqual(insert.call_args.args[2][0][:2], ("E", "E2025"))
        failing = FakeConnection()
        with patch("gold_etl.loader.read_aggregate_rows", return_value=[stored_row()]), \
                patch("psycopg2.extras.execute_values", side_effect=RuntimeError("failed")):
            with self.assertRaisesRegex(RuntimeError, "failed"):
                replace_aggregate_scope(failing, "player_round_stats", "E", "E2025")
        self.assertEqual((failing.commits, failing.rollbacks), (0, 1))

    def test_read_rows_queries_the_player_silver_tables(self):
        from gold_etl import player_rounds

        db = FakeConnection()
        games, boxes, players = full_game()
        tables = [games, [r for rows, _ in boxes for r in rows],
                  [r for _, rows in boxes for r in rows], []]
        with patch.object(player_rounds, "read_tables", return_value=tables), \
                patch.object(player_rounds, "_dict_rows", side_effect=[players, []]):
            rows = player_rounds.read_rows(db.cursor(), "E", "E2025")
        sql = " ".join(query for query, _ in db.queries)
        self.assertIn("silver.game_player_stats", sql)
        self.assertIn("silver.game_player_advanced", sql)
        self.assertTrue(rows)

    def test_quality_compares_a_fresh_derivation(self):
        from gold_etl.quality import check_aggregate_scope

        db, expected = FakeConnection(), stored_row()
        cursor = db.cursor()
        db.exists = False
        self.assertEqual(check_aggregate_scope(cursor, "player_round_stats", "E", "E2025"),
                         ["gold.app_player_round_stats is missing"])
        db.exists = True
        with patch("gold_etl.quality.read_aggregate_rows", return_value=[expected]):
            for actual, message in (([], "keys differ"),
                                    ([dict(expected, points=Decimal(999))], "values differ"),
                                    ([expected], None)):
                with patch("gold_etl.quality._dict_rows", return_value=actual):
                    issues = check_aggregate_scope(cursor, "player_round_stats", "E", "E2025")
                    self.assertEqual(issues == [], message is None)
                    if message:
                        self.assertIn(message, issues[0])


class ApiCrossCheckTests(unittest.TestCase):
    COUNTS = dict(games_played=10, points=100, three_pointers_made=10, free_throws_made=20,
                  free_throws_attempted=25, offensive_rebounds=8, defensive_rebounds=30,
                  total_rebounds=38, assists=20, steals=6, turnovers=15, blocks=3,
                  fouls_committed=22, pir=90)

    def run_check(self, ours, traditional, advanced):
        from gold_etl.quality import check_round_player_api_scope

        with patch("gold_etl.quality._dict_rows", side_effect=[ours, traditional, advanced]):
            return check_round_player_api_scope(FakeConnection().cursor(), "E", "E2025")

    def final(self, scope="RS", **changes):
        row = dict({name: Decimal(value) for name, value in self.COUNTS.items()},
                   scope=scope, person_key="P1", seconds_played=Decimal(9000),
                   efg_pct=Decimal("0.5500"), ts_pct=Decimal("0.6000"),
                   orb_pct=Decimal("0.0500"), drb_pct=Decimal("0.2000"),
                   trb_pct=Decimal("0.1200"))
        return dict(row, **changes)

    def feeds(self, phase="RS", **changes):
        traditional = dict({name: Decimal(value) for name, value in self.COUNTS.items()},
                           phase_code=phase, person_key="P1", minutes_played=Decimal("150.0"))
        advanced = {"phase_code": phase, "person_key": "P1",
                    "effective_field_goal_percentage": Decimal("55.0"),
                    "true_shooting_percentage": Decimal("60.0"),
                    "offensive_rebounds_percentage": Decimal("5.0"),
                    "defensive_rebounds_percentage": Decimal("20.0"),
                    "rebounds_percentage": Decimal("12.0")}
        return [dict(traditional, **changes)], [advanced]

    def test_matching_rows_report_nothing(self):
        self.assertEqual(self.run_check([self.final()], *self.feeds()), [])

    def test_count_minutes_and_rate_mismatches_are_reported(self):
        traditional, advanced = self.feeds(points=Decimal(101), minutes_played=Decimal("151"))
        advanced[0]["offensive_rebounds_percentage"] = Decimal("9.0")
        issues = self.run_check([self.final()], traditional, advanced)
        text = " | ".join(issues)
        for metric in ("points differs", "minutes differs", "orb_pct differs"):
            self.assertIn(metric, text)
        self.assertEqual(len(issues), 3)

    def test_small_rate_differences_within_tolerance_pass(self):
        traditional, advanced = self.feeds()
        advanced[0]["rebounds_percentage"] = Decimal("13.5")           # within 2 points
        advanced[0]["effective_field_goal_percentage"] = Decimal("55.05")
        self.assertEqual(self.run_check([self.final()], traditional, advanced), [])

    def test_rates_are_skipped_below_the_minutes_threshold(self):
        traditional, advanced = self.feeds(minutes_played=Decimal("50"))
        advanced[0]["effective_field_goal_percentage"] = Decimal("10")
        self.assertEqual(self.run_check([self.final(seconds_played=Decimal(3000))],
                                        traditional, advanced), [])

    def test_missing_api_row_scope_without_feed_and_null_values_are_skipped(self):
        self.assertEqual(self.run_check([self.final("PS")], *self.feeds()), [])
        self.assertEqual(self.run_check([self.final(points=None)],
                                        *self.feeds(points=Decimal(1))), [])


if __name__ == "__main__":
    unittest.main()
