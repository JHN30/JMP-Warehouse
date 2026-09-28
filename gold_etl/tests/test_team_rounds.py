"""Cumulative team-round rows: scopes, carry-forward, formulas, and storage."""

import sys
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from gold_etl.schema import ROUND_MEASURES, TEAM_ROUND_TABLE, columns
from gold_etl.team_rounds import PYTHAGOREAN_EXPONENT, derive_rows

MEASURES = dict(points=83, field_goals_made=30, field_goals_attempted=60,
                three_pointers_made=8, free_throws_made=15, free_throws_attempted=20,
                offensive_rebounds=10, defensive_rebounds=25, turnovers=12, assists=15)
OTHER = dict(points=74, field_goals_made=28, field_goals_attempted=62,
             three_pointers_made=6, free_throws_made=12, free_throws_attempted=16,
             offensive_rebounds=9, defensive_rebounds=22, turnovers=10, assists=12)


def game(code, round_number, phase="RS", local="MAD", road="BAR", winner="MAD",
         played=True):
    return {"game_code": code, "phase_code": phase, "round_number": round_number,
            "played": played, "local_club_code": local, "road_club_code": road,
            "local_club_name": local + " game", "road_club_name": road + " game",
            "match_winner_club_code": winner}


def box(code, local=MEASURES, road=OTHER, possessions="70.42", minutes=40):
    rows = []
    for side, values in (("local", local), ("road", road)):
        rows.append(dict(values, game_code=code, side=side, stats_kind="total"))
    advanced = [{"game_code": code, "side": side, "possessions": Decimal(possessions),
                 "game_minutes": Decimal(minutes)} for side in ("local", "road")]
    return rows, advanced


def derive(games, boxes, clubs=()):
    stats = [row for rows, _ in boxes for row in rows]
    advanced = [row for _, rows in boxes for row in rows]
    return derive_rows(games, stats, advanced, list(clubs))


def pick(rows, scope, round_number, club):
    return next(row for row in rows if (row["scope"], row["round_number"], row["club_code"])
                == (scope, round_number, club))


class ScopeTests(unittest.TestCase):
    def test_all_phase_and_ps_scopes(self):
        games = [game(1, 1), game(2, 39, "PI"), game(3, 41, "PO"), game(4, 46, "FF")]
        rows = derive(games, [box(code) for code in (1, 2, 3, 4)])
        scopes = {row["scope"] for row in rows}
        self.assertEqual(scopes, {"all", "RS", "PI", "PO", "FF", "PS"})
        self.assertEqual([r["round_number"] for r in rows if r["scope"] == "PS"
                          and r["club_code"] == "MAD"], [39, 41, 46])
        self.assertEqual(pick(rows, "PS", 46, "MAD")["games_played"], 3)
        self.assertEqual(pick(rows, "all", 46, "MAD")["games_played"], 4)
        self.assertEqual(pick(rows, "RS", 1, "MAD")["games_played"], 1)

    def test_idle_club_carries_forward_and_late_club_has_no_earlier_rows(self):
        games = [game(1, 1), game(2, 2, local="MAD", road="RMA", winner="RMA"),
                 game(3, 3, local="BAR", road="RMA", winner="BAR")]
        rows = derive(games, [box(code) for code in (1, 2, 3)])
        bar = [r for r in rows if r["scope"] == "RS" and r["club_code"] == "BAR"]
        self.assertEqual([(r["round_number"], r["games_played"]) for r in bar],
                         [(1, 1), (2, 1), (3, 2)])
        self.assertEqual(bar[0]["own_field_goals_made"], bar[1]["own_field_goals_made"])
        rma = [r["round_number"] for r in rows if r["scope"] == "RS" and r["club_code"] == "RMA"]
        self.assertEqual(rma, [2, 3])
        madrid = pick(rows, "RS", 3, "MAD")
        self.assertEqual((madrid["wins"], madrid["losses"]), (1, 1))

    def test_uncounted_games_are_skipped(self):
        games = [game(1, 1), game(2, 2, played=False), game(3, 3), game(4, 4)]
        one_side = box(3)
        no_advanced = box(4)
        boxes = [box(1), box(2), (one_side[0][:1], one_side[1]), (no_advanced[0], [])]
        rows = derive(games, boxes)
        self.assertEqual({r["round_number"] for r in rows}, {1})

    def test_club_name_prefers_clubs_table_then_game_name(self):
        rows = derive([game(1, 1)], [box(1)], [{"club_code": "MAD", "name": "Real Madrid"}])
        self.assertEqual(pick(rows, "all", 1, "MAD")["club_name"], "Real Madrid")
        self.assertEqual(pick(rows, "all", 1, "BAR")["club_name"], "BAR game")


class FormulaTests(unittest.TestCase):
    def setUp(self):
        games = [game(1, 1), game(2, 2, local="BAR", road="MAD", winner="BAR")]
        boxes = [box(1), box(2, local=OTHER, road=MEASURES, possessions="70.0")]
        self.rows = derive(games, boxes)

    def test_first_round_matches_one_game(self):
        row = pick(self.rows, "all", 1, "MAD")
        self.assertEqual(row["possessions"], Decimal("70.42"))
        self.assertEqual(row["game_minutes"], 40)
        self.assertEqual(row["pace"], Decimal("70.420000"))
        self.assertEqual(row["mov"], 9)
        self.assertEqual(row["efg_pct"], Decimal("0.566667"))
        self.assertEqual(row["orb_pct"], Decimal("0.312500"))
        self.assertEqual(row["drb_pct"], Decimal("0.735294"))
        self.assertEqual(row["ft_rate"], Decimal("0.250000"))
        self.assertEqual(row["assist_ratio"], Decimal("0.500000"))
        self.assertAlmostEqual(float(row["offensive_rating"]), 117.86, places=2)

    def test_two_game_cumulative_totals_and_rates(self):
        row = pick(self.rows, "all", 2, "MAD")
        self.assertEqual((row["games_played"], row["wins"], row["losses"]), (2, 1, 1))
        self.assertEqual((row["points_for"], row["points_against"]), (166, 148))
        self.assertEqual(row["own_field_goals_attempted"], 120)
        self.assertEqual(row["opp_field_goals_attempted"], 124)
        self.assertEqual(row["possessions"], Decimal("140.42"))
        self.assertEqual(row["game_minutes"], 80)
        self.assertEqual(row["mov"], 9)
        expected = 166 ** 10.25 / (166 ** 10.25 + 148 ** 10.25)
        self.assertAlmostEqual(float(row["pythagorean_win_pct"]), expected, places=5)
        self.assertAlmostEqual(float(row["pythagorean_wins"]), 2 * expected, places=5)
        self.assertEqual(row["pythagorean_exponent"], PYTHAGOREAN_EXPONENT)
        self.assertAlmostEqual(float(row["pace"]), 40 * 140.42 / 80, places=5)
        self.assertAlmostEqual(float(row["offensive_rating"]), 100 * 166 / 140.42, places=4)
        self.assertAlmostEqual(float(row["defensive_rating"]), 100 * 148 / 140.42, places=4)
        self.assertAlmostEqual(float(row["net_rating"]), 100 * 18 / 140.42, places=4)
        self.assertAlmostEqual(float(row["efg_pct"]), (60 + 8) / 120, places=5)
        self.assertAlmostEqual(float(row["orb_pct"]), 20 / (20 + 44), places=5)
        self.assertAlmostEqual(float(row["tov_pct"]), 24 / (120 + 0.44 * 40 + 24), places=5)
        self.assertAlmostEqual(float(row["opp_ft_rate"]), 24 / 124, places=5)

    def test_pythagorean_uses_the_exponent(self):
        row = pick(self.rows, "all", 1, "MAD")
        expected = 83 ** 10.25 / (83 ** 10.25 + 74 ** 10.25)
        self.assertAlmostEqual(float(row["pythagorean_win_pct"]), expected, places=5)

    def test_missing_input_or_zero_denominator_gives_null(self):
        broken = dict(OTHER, offensive_rebounds=None)
        rows = derive([game(1, 1), game(2, 2)], [box(1), box(2, road=broken)])
        first, second = pick(rows, "all", 1, "MAD"), pick(rows, "all", 2, "MAD")
        self.assertIsNotNone(first["orb_pct"])
        self.assertIsNone(second["opp_offensive_rebounds"])
        self.assertIsNone(second["drb_pct"])
        self.assertEqual(second["own_field_goals_made"], 60)
        empty = dict(MEASURES, field_goals_attempted=0)
        zero = derive([game(1, 1)], [box(1, local=empty)])
        self.assertIsNone(pick(zero, "all", 1, "MAD")["efg_pct"])

    def test_final_possessions_equal_the_sum_of_game_values(self):
        row = pick(self.rows, "all", 2, "BAR")
        self.assertEqual(row["possessions"], Decimal("70.42") + Decimal("70.0"))

    def test_first_round_matches_feature_25_game_values(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "postgres_etl"))
        try:
            import advanced
        finally:
            sys.path.pop(0)
        detail = {"points": "points", "field_goals_made": "field_goals_made",
                  "field_goals_attempted": "field_goals_attempted",
                  "three_pointers_made": "three_pointers_made",
                  "free_throws_made": "free_throws_made",
                  "free_throws_attempted": "free_throws_attempted",
                  "offensive_rebounds": "offensive_rebounds",
                  "defensive_rebounds": "defensive_rebounds",
                  "turnovers": "turnovers", "assists": "assists"}
        totals = [dict({k: MEASURES[k] for k in detail}, three_pointers_attempted=20,
                       total_rebounds=35, steals=6, blocks=3, fouls_committed=18,
                       game_code=1, side="local", stats_kind="total"),
                  dict({k: OTHER[k] for k in detail}, three_pointers_attempted=18,
                       total_rebounds=31, steals=5, blocks=2, fouls_committed=20,
                       game_code=1, side="road", stats_kind="total")]
        team, _ = advanced.derive_rows([game(1, 1)], [], totals, [], [])
        rows = derive_rows([game(1, 1)], totals, team, [])
        mad, per_game = pick(rows, "all", 1, "MAD"), team[0]
        for column in ("possessions", "pace", "offensive_rating", "defensive_rating",
                       "net_rating", "efg_pct", "tov_pct", "orb_pct", "drb_pct",
                       "ft_rate", "opp_efg_pct", "opp_tov_pct", "opp_ft_rate",
                       "true_shooting_pct", "assist_ratio"):
            self.assertEqual(mad[column], per_game[column], column)


class SchemaTests(unittest.TestCase):
    def test_every_derived_key_is_a_registered_column(self):
        rows = derive([game(1, 1)], [box(1)])
        self.assertEqual(set(rows[0]) | {"competition_code", "season_code"},
                         set(columns("team_round_stats")))
        self.assertEqual(TEAM_ROUND_TABLE.key[-3:], ("scope", "round_number", "club_code"))
        self.assertEqual(len(ROUND_MEASURES), 9)

    def test_table_is_outside_the_publish_allowlist(self):
        from gold_etl.schema import DERIVED_NAMES, SOURCE_NAMES

        self.assertNotIn("team_round_stats", DERIVED_NAMES + SOURCE_NAMES)


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
    row = derive([game(1, 1)], [box(1)])[0]
    return dict(row, competition_code="E", season_code="E2025")


class StorageTests(unittest.TestCase):
    def test_replace_is_scoped_and_atomic(self):
        from gold_etl.loader import replace_aggregate_scope

        db = FakeConnection()
        with patch("gold_etl.loader.read_aggregate_rows", return_value=[stored_row()]),                 patch("psycopg2.extras.execute_values") as insert:
            self.assertEqual(replace_aggregate_scope(db, "team_round_stats", "E", "E2025"), 1)
        self.assertEqual((db.commits, db.rollbacks), (1, 0))
        self.assertTrue(any(query.startswith('DELETE FROM gold."team_round_stats"')
                            and params == ("E", "E2025") for query, params in db.queries))
        self.assertEqual(insert.call_args.args[2][0][:2], ("E", "E2025"))

    def test_failure_rolls_back(self):
        from gold_etl.loader import replace_aggregate_scope

        db = FakeConnection()
        with patch("gold_etl.loader.read_aggregate_rows", return_value=[stored_row()]),                 patch("psycopg2.extras.execute_values", side_effect=RuntimeError("failed")):
            with self.assertRaisesRegex(RuntimeError, "failed"):
                replace_aggregate_scope(db, "team_round_stats", "E", "E2025")
        self.assertEqual((db.commits, db.rollbacks), (0, 1))

    def test_read_rows_queries_the_four_silver_tables(self):
        from gold_etl import team_rounds

        db = FakeConnection()
        cursor = db.cursor()
        with patch.object(team_rounds, "_dict_rows", return_value=[]):
            self.assertEqual(team_rounds.read_rows(cursor, "E", "E2025"), [])
        sql = [query for query, _ in db.queries]
        for table in ("games", "game_team_stats", "game_team_advanced", "clubs"):
            self.assertTrue(any(f"silver.{table} " in query for query in sql), table)
        self.assertTrue(all(params == ("E", "E2025") for _, params in db.queries))

    def test_quality_detects_missing_keys_and_values(self):
        from gold_etl.quality import check_aggregate_scope

        db, expected = FakeConnection(), stored_row()
        cursor = db.cursor()
        db.exists = False
        self.assertEqual(check_aggregate_scope(cursor, "team_round_stats", "E", "E2025"),
                         ["gold.team_round_stats is missing"])
        db.exists = True
        with patch("gold_etl.quality.read_aggregate_rows", return_value=[expected]):
            for actual, message in (([], "keys differ"),
                                    ([dict(expected, wins=9)], "values differ"),
                                    ([expected], None)):
                with patch("gold_etl.quality._dict_rows", return_value=actual):
                    issues = check_aggregate_scope(cursor, "team_round_stats", "E", "E2025")
                    self.assertEqual(issues == [], message is None)
                    if message:
                        self.assertIn(message, issues[0])


class ApiCrossCheckTests(unittest.TestCase):
    def run_check(self, ours, traditional, advanced):
        from gold_etl.quality import check_round_api_scope

        with patch("gold_etl.quality._dict_rows", side_effect=[ours, traditional, advanced]):
            return check_round_api_scope(FakeConnection().cursor(), "E", "E2025")

    def final(self, scope="RS", **changes):
        row = {"scope": scope, "club_code": "MAD", "games_played": 2, "points_for": 166,
               "own_three_pointers_made": 16, "own_free_throws_made": 30,
               "own_free_throws_attempted": 40, "own_offensive_rebounds": 20,
               "own_defensive_rebounds": 50, "own_turnovers": 24, "own_assists": 30,
               "efg_pct": Decimal("0.566667"), "true_shooting_pct": Decimal("0.6"),
               "orb_pct": Decimal("0.3125"), "drb_pct": Decimal("0.7353")}
        return dict(row, **changes)

    def feeds(self, phase="RS", **changes):
        traditional = {"phase_code": phase, "club_code": "MAD", "games_played": Decimal("2.0"),
                       "points": Decimal("166"), "three_pointers_made": Decimal("16"),
                       "free_throws_made": Decimal("30"), "free_throws_attempted": Decimal("40"),
                       "offensive_rebounds": Decimal("20"), "defensive_rebounds": Decimal("50"),
                       "turnovers": Decimal("24"), "assists": Decimal("30")}
        advanced = {"phase_code": phase, "club_code": "MAD",
                    "effective_field_goal_percentage": Decimal("56.7"),
                    "true_shooting_percentage": Decimal("60.0"),
                    "offensive_rebounds_percentage": Decimal("31.3"),
                    "defensive_rebounds_percentage": Decimal("73.5")}
        return [dict(traditional, **changes)], [advanced]

    def test_matching_rows_within_rounding_report_nothing(self):
        self.assertEqual(self.run_check([self.final()], *self.feeds()), [])

    def test_count_and_rate_mismatches_are_reported(self):
        issues = self.run_check([self.final(points_for=170, efg_pct=Decimal("0.60"))],
                                *self.feeds())
        self.assertEqual(len(issues), 2)
        self.assertTrue(any("points_for differs" in issue and "MAD: 170 vs API 166" in issue
                            for issue in issues))
        self.assertTrue(any("efg_pct differs" in issue for issue in issues))

    def test_scope_without_an_api_feed_is_skipped(self):
        self.assertEqual(self.run_check([self.final("PS", points_for=1)], *self.feeds()), [])

    def test_missing_values_are_skipped(self):
        self.assertEqual(self.run_check([self.final(points_for=None)],
                                        *self.feeds(points=Decimal("1"))), [])


if __name__ == "__main__":
    unittest.main()
