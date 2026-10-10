"""Cumulative PER: league constants, the player formula, normalization, storage, quality."""

import unittest
from decimal import Decimal
from unittest.mock import patch

from gold_etl.player_ratings import derive_rows
from gold_etl.schema import columns
from gold_etl.tests.test_player_rounds import (LOCAL, ROAD, STAR, FakeConnection, box, game,
                                               minus, player)

# Both clubs of the 70.42-possession, 40-minute game in test_player_rounds:
# PTS 157, FGM 58, FGA 122, FTM 27, FTA 36, ORB 19, TRB 66, AST 27, TOV 22, PF 38.
FACTOR = 2 / 3 - (0.5 * 27 / 58) / (2 * 58 / 27)
VOP = 157 / (122 - 19 + 22 + 0.44 * 36)
DRB = (66 - 19) / 66
FOUL = 27 / 38 - 0.44 * (36 / 38) * VOP


def derive(games, boxes, players):
    stats = [row for rows, _ in boxes for row in rows]
    advanced = [row for _, rows in boxes for row in rows]
    return derive_rows(games, stats, advanced, [], players)


def pick(rows, scope, round_number, key):
    return next(row for row in rows if (row["scope"], row["round_number"], row["person_key"])
                == (scope, round_number, key))


def hand_uper(p, seconds, team_ast, team_fg):
    """The published formula written out with floats, for the star of the first game."""
    ratio = team_ast / team_fg
    total = (3 * p["three_pointers_made"] + 2 / 3 * p["assists"]
             + (2 - FACTOR * ratio) * p["field_goals_made"]
             + 0.5 * p["free_throws_made"] * (2 - ratio / 3)
             - VOP * p["turnovers"]
             - VOP * DRB * (p["field_goals_attempted"] - p["field_goals_made"])
             - VOP * 0.44 * (0.44 + 0.56 * DRB)
             * (p["free_throws_attempted"] - p["free_throws_made"])
             + VOP * (1 - DRB) * (p["total_rebounds"] - p["offensive_rebounds"])
             + VOP * DRB * p["offensive_rebounds"] + VOP * p["steals"]
             + VOP * DRB * p["blocks"] - p["fouls_committed"] * FOUL)
    return total / (seconds / 60)


def one_game(code=1, round_number=1, phase="RS", star_seconds=1200):
    bench = dict(minus(LOCAL, STAR), seconds_played=12000 - star_seconds)
    players = [player(code, "P1", started=True, **dict(STAR, seconds_played=star_seconds)),
               player(code, "P2", **bench),
               player(code, "R1", side="road", club="BAR", **dict(ROAD, seconds_played=12000))]
    return [game(code, round_number, phase=phase)], [box(code)], players


class FormulaTests(unittest.TestCase):
    def test_star_uper_and_aper_match_the_hand_formula(self):
        rows = derive(*one_game())
        star = pick(rows, "all", 1, "P1")
        uper = hand_uper(STAR, 1200, LOCAL["assists"], LOCAL["field_goals_made"])
        self.assertAlmostEqual(float(star["uper"]), uper, places=4)
        # League pace equals the team pace here, so the pace adjustment is 1.
        self.assertAlmostEqual(float(star["aper"]), uper, places=4)
        self.assertEqual(star["games_played"], 1)
        self.assertEqual(star["seconds_played"], 1200)
        self.assertEqual({"scope", "round_number", "person_key", "uper", "aper", "per"}
                         - set(columns("player_round_ratings")), set())

    def test_per_is_normalized_so_the_seconds_weighted_league_mean_is_15(self):
        games, boxes, players = one_game()
        games += [game(2, 2, local="BAR", road="MAD")]
        boxes += [box(2, local=ROAD, road=LOCAL, possessions="80", minutes=45)]
        players += [player(2, "P1", side="road", club="MAD", **dict(STAR, seconds_played=1500)),
                    player(2, "R1", side="local", club="BAR",
                           **dict(ROAD, seconds_played=13500))]
        rows = derive(games, boxes, players)
        for round_number in (1, 2):
            group = [r for r in rows if r["scope"] == "all" and r["round_number"] == round_number]
            seconds = sum(float(r["seconds_played"]) for r in group)
            mean = sum(float(r["per"]) * float(r["seconds_played"]) for r in group) / seconds
            self.assertAlmostEqual(mean, 15, places=4)

    def test_pace_adjustment_scales_by_league_pace_over_the_players_team_pace(self):
        games, boxes, players = one_game()
        games += [game(2, 2, local="BAR", road="MAD")]
        boxes += [box(2, local=ROAD, road=LOCAL, possessions="90", minutes=40)]
        players += [player(2, "R1", side="local", club="BAR", **dict(ROAD, seconds_played=12000))]
        star = pick(derive(games, boxes, players), "all", 2, "P1")
        # P1 only played the 70.42-possession game; league pace after round 2 is
        # 40 x (2 x 70.42 + 2 x 90) / 160 minutes.
        league_pace = 40 * (2 * 70.42 + 2 * 90) / 160
        self.assertAlmostEqual(float(star["aper"]) / float(star["uper"]),
                               league_pace / 70.42, places=4)

    def test_idle_rounds_carry_totals_but_use_that_rounds_league_constants(self):
        games, boxes, players = one_game()
        games += [game(2, 2, local="BAR", road="MAD")]
        boxes += [box(2, local=dict(ROAD, turnovers=30), road=LOCAL, possessions="80", minutes=40)]
        players += [player(2, "R1", side="local", club="BAR", **dict(ROAD, seconds_played=12000))]
        rows = derive(games, boxes, players)
        first, carried = pick(rows, "all", 1, "P1"), pick(rows, "all", 2, "P1")
        self.assertEqual((carried["games_played"], carried["seconds_played"]), (1, 1200))
        self.assertNotEqual(first["uper"], carried["uper"])
        self.assertIsNone(next((r for r in rows if r["round_number"] == 1
                                and r["person_key"] == "R2"), None))

    def test_transfer_keeps_one_row_with_the_latest_club_and_own_game_context(self):
        games, boxes, players = one_game()
        games += [game(2, 2, local="BAR", road="MAD")]
        boxes += [box(2)]
        players += [player(2, "P1", side="local", club="BAR", **dict(STAR, seconds_played=1200))]
        rows = [r for r in derive(games, boxes, players)
                if r["scope"] == "all" and r["person_key"] == "P1"]
        self.assertEqual([r["club_code"] for r in rows], ["MAD", "BAR"])
        self.assertEqual(rows[-1]["games_played"], 2)

    def test_missing_input_and_zero_denominators_are_null(self):
        games, boxes, players = one_game()
        players[0]["assists"] = None
        rows = derive(games, boxes, players)
        star = pick(rows, "all", 1, "P1")
        self.assertEqual((star["uper"], star["aper"], star["per"]), (None, None, None))
        self.assertIsNotNone(pick(rows, "all", 1, "P2")["per"])
        games, boxes, players = one_game()
        boxes[0][0][0]["field_goals_made"] = 0          # league and team field goals fall
        boxes[0][0][1]["field_goals_made"] = 0
        self.assertIsNone(pick(derive(games, boxes, players), "all", 1, "P1")["per"])

    def test_scopes_and_did_not_play(self):
        games, boxes, players = one_game(phase="PO")
        players.append(player(1, "DNP", seconds_played=0))
        rows = derive(games, boxes, players)
        self.assertEqual({r["scope"] for r in rows}, {"all", "PO", "PS"})
        self.assertFalse([r for r in rows if r["person_key"] == "DNP"])


def stored_row():
    return dict(derive(*one_game())[0], competition_code="E", season_code="E2025")


class StorageTests(unittest.TestCase):
    def test_replace_is_scoped_atomic_and_rolls_back(self):
        from gold_etl.loader import replace_aggregate_scope

        db = FakeConnection()
        with patch("gold_etl.loader.read_aggregate_rows", return_value=[stored_row()]), \
                patch("psycopg2.extras.execute_values") as insert:
            self.assertEqual(replace_aggregate_scope(db, "player_round_ratings", "E", "E2025"), 1)
        self.assertEqual((db.commits, db.rollbacks), (1, 0))
        self.assertTrue(any(query.startswith('DELETE FROM gold."app_player_round_ratings"')
                            and params == ("E", "E2025") for query, params in db.queries))
        self.assertEqual(insert.call_args.args[2][0][:2], ("E", "E2025"))
        failing = FakeConnection()
        with patch("gold_etl.loader.read_aggregate_rows", return_value=[stored_row()]), \
                patch("psycopg2.extras.execute_values", side_effect=RuntimeError("failed")):
            with self.assertRaisesRegex(RuntimeError, "failed"):
                replace_aggregate_scope(failing, "player_round_ratings", "E", "E2025")
        self.assertEqual((failing.commits, failing.rollbacks), (0, 1))

    def test_read_rows_dispatches_and_queries_player_stats(self):
        from gold_etl import player_ratings
        from gold_etl.loader import read_aggregate_rows

        db = FakeConnection()
        games, boxes, players = one_game()
        tables = [games, [r for rows, _ in boxes for r in rows],
                  [r for _, rows in boxes for r in rows], []]
        with patch.object(player_ratings, "read_tables", return_value=tables), \
                patch.object(player_ratings, "_dict_rows", return_value=players):
            rows = read_aggregate_rows(db.cursor(), "player_round_ratings", "E", "E2025")
        self.assertIn("silver.game_player_stats", " ".join(q for q, _ in db.queries))
        self.assertTrue(rows)

    def test_player_rows_are_fetched_before_read_tables_reuses_the_cursor(self):
        from gold_etl import player_ratings

        order = []
        games, boxes, players = one_game()
        tables = [games, [r for rows, _ in boxes for r in rows],
                  [r for _, rows in boxes for r in rows], []]

        def fetch(cursor):
            order.append("fetch")
            return players

        def tables_read(*_):
            order.append("tables")
            return tables

        with patch.object(player_ratings, "read_tables", side_effect=tables_read),                 patch.object(player_ratings, "_dict_rows", side_effect=fetch):
            player_ratings.read_rows(FakeConnection().cursor(), "E", "E2025")
        self.assertEqual(order, ["fetch", "tables"])

    def test_quality_compares_a_fresh_derivation(self):
        from gold_etl.quality import check_aggregate_scope

        db, expected = FakeConnection(), stored_row()
        cursor = db.cursor()
        with patch("gold_etl.quality.read_aggregate_rows", return_value=[expected]):
            for actual, message in (([], "keys differ"),
                                    ([dict(expected, per=Decimal(99))], "values differ"),
                                    ([expected], None)):
                with patch("gold_etl.quality._dict_rows", return_value=actual):
                    issues = check_aggregate_scope(cursor, "player_round_ratings", "E", "E2025")
                    self.assertEqual(issues == [], message is None)
                    if message:
                        self.assertIn(message, issues[0])

    def test_invariant_flags_a_wrong_league_mean_but_allows_negative_per(self):
        from gold_etl.quality import check_round_player_rating_invariants

        cursor = FakeConnection().cursor()

        def issues(rows):
            with patch("gold_etl.quality._dict_rows", return_value=rows):
                return check_round_player_rating_invariants(cursor, "E", "E2025")

        def row(key, seconds, per):
            return {"scope": "all", "round_number": 1, "person_key": key,
                    "seconds_played": Decimal(seconds), "per": per}

        good = [row("A", 600, Decimal("20")), row("B", 1800, Decimal("13.333333"))]
        self.assertEqual(issues(good), [])
        self.assertEqual(issues([row("A", 600, None)]), [])
        self.assertIn("not 15", issues([row("A", 600, Decimal("20")), row("B", 600, Decimal("20"))])[0])
        self.assertEqual(issues([row("A", 60, Decimal("-1")), row("B", 60, Decimal("31"))]), [])


if __name__ == "__main__":
    unittest.main()
