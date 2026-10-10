"""RAPM: ridge fit on synthetic seasons with planted effects, folds, storage, registration."""

import random
import sys
import unittest
from decimal import Decimal
from unittest.mock import patch

import numpy as np

from gold_etl import rapm
from gold_etl.schema import GOLD_TABLES, ROUND_NAMES, columns
from gold_etl.tests.test_team_splits import FakeConnection

TEAMS = {team: [f"{team}{number}" for number in range(8)] for team in "ABCDEF"}
OFFENSE = {"A0": 5.0}
DEFENSE = {"B0": 5.0}
GRID = (1, 10, 100, 1000)


def synthetic(games=60, stints_per_game=8, seed=7):
    """Stint rows (both sides) whose points per 100 possessions follow the planted model."""
    rng = random.Random(seed)
    rows = []
    for game in range(1, games + 1):
        home, road = rng.sample(sorted(TEAMS), 2)
        for stint in range(1, stints_per_game + 1):
            lineups = {home: sorted(rng.sample(TEAMS[home], 5)),
                       road: sorted(rng.sample(TEAMS[road], 5))}
            for own, other in ((home, road), (road, home)):
                value = 100 + sum(OFFENSE.get(p, 0) for p in lineups[own]) \
                    - sum(DEFENSE.get(p, 0) for p in lineups[other])
                rows.append({"game_code": game, "club_code": own, "stint_ordinal": stint,
                             "players": ",".join(lineups[own]),
                             "opponent_players": ",".join(lineups[other]),
                             "start_seconds": (stint - 1) * 300, "end_seconds": stint * 300,
                             "possessions_for": 100, "possessions_against": 100,
                             "points_for": value, "points_against": 0})
    return rows


GAMES = [{"game_code": code, "played": True} for code in range(1, 61)]
STINTS = synthetic()
PLAYERS = [{"person_key": "A0", "person_name": "ALPHA, A"}]
ROWS = rapm.derive_rows(GAMES, STINTS, PLAYERS, penalties=GRID)


def pick(rows, person):
    return next(row for row in rows if row["person_key"] == person)


class FitTests(unittest.TestCase):
    def test_a_planted_offensive_and_defensive_effect_are_recovered_with_their_signs(self):
        alpha, bravo = pick(ROWS, "A0"), pick(ROWS, "B0")
        self.assertAlmostEqual(float(alpha["offense"]), 5.0, delta=0.5)
        self.assertAlmostEqual(float(bravo["defense"]), 5.0, delta=0.5)
        self.assertEqual(max(ROWS, key=lambda r: r["offense"])["person_key"], "A0")
        self.assertEqual(max(ROWS, key=lambda r: r["defense"])["person_key"], "B0")
        others = [r for r in ROWS if r["person_key"] not in ("A0", "B0")]
        self.assertLess(max(abs(float(r["offense"])) for r in others
                            if r["person_key"] != "A0"), 1.0)
        self.assertEqual(alpha["rapm"], alpha["offense"] + alpha["defense"])

    def test_the_penalty_is_chosen_from_the_grid_and_stored_on_every_row(self):
        self.assertIn(ROWS[0]["penalty"], [Decimal(value) for value in GRID])
        self.assertEqual({row["penalty"] for row in ROWS}, {ROWS[0]["penalty"]})
        default = rapm.derive_rows(GAMES, STINTS, PLAYERS)
        self.assertIn(default[0]["penalty"], [Decimal(value) for value in rapm.PENALTIES])

    def test_flat_cross_validation_errors_choose_the_strongest_penalty(self):
        flat = [dict(row, points_for=100) for row in STINTS]
        rows = rapm.derive_rows(GAMES, flat, PLAYERS, penalties=GRID)
        self.assertEqual({row["penalty"] for row in rows}, {Decimal(GRID[-1])})
        self.assertEqual({row["rapm"] for row in rows}, {Decimal("0.0000")})

    def test_a_larger_penalty_shrinks_the_coefficients(self):
        rows = [row for row in STINTS if row["game_code"] <= 30]
        people = sorted({p for r in rows for p in r["players"].split(",")})
        position = {person: number for number, person in enumerate(people)}
        count = len(people)
        index = np.array([[position[p] for p in r["players"].split(",")]
                          + [count + position[p] for p in r["opponent_players"].split(",")]
                          for r in rows])
        sign = np.array([1.0] * 5 + [-1.0] * 5)
        weight = np.array([float(r["possessions_for"]) for r in rows])
        value = np.array([100.0 * r["points_for"] / r["possessions_for"] for r in rows])
        norms = []
        for penalty in (1, 1000, 100000):
            chosen, _, beta = rapm._fit(np, index, sign, weight, value, 2 * count, penalty)
            self.assertEqual(chosen, penalty)
            norms.append(float(np.linalg.norm(beta)))
        self.assertGreater(norms[0], norms[1])
        self.assertGreater(norms[1], norms[2])

    def test_folds_hold_out_whole_games(self):
        seen = {}

        original = rapm._fit

        def capture(*args):
            seen["folds"] = args[7]
            return original(*args)

        with patch.object(rapm, "_fit", capture):
            rapm.derive_rows(GAMES, STINTS, PLAYERS, penalties=GRID)
        folds = seen["folds"]
        by_game = {}
        for row, fold in zip(STINTS, folds):
            by_game.setdefault(row["game_code"], set()).add(int(fold))
        self.assertTrue(all(len(value) == 1 for value in by_game.values()))
        self.assertEqual(set(map(int, folds)), set(range(rapm.FOLDS)))


class InputTests(unittest.TestCase):
    def test_empty_and_zero_possession_input_give_no_rows(self):
        self.assertEqual(rapm.derive_rows([], [], []), [])
        empty = [dict(row, possessions_for=0) for row in STINTS]
        self.assertEqual(rapm.derive_rows(GAMES, empty, PLAYERS), [])

    def test_unplayed_games_and_incomplete_lineups_are_ignored(self):
        self.assertEqual(rapm.derive_rows([dict(g, played=False) for g in GAMES], STINTS,
                                          PLAYERS), [])
        short = [dict(row, players="A0,A1,A2,A3") for row in STINTS]
        self.assertEqual(rapm.derive_rows(GAMES, short, PLAYERS), [])

    def test_seconds_possessions_and_names(self):
        alpha = pick(ROWS, "A0")
        mine = [r for r in STINTS if "A0" in r["players"].split(",")]
        against = [r for r in STINTS if "A0" in r["opponent_players"].split(",")]
        self.assertEqual(alpha["seconds"], sum(r["end_seconds"] - r["start_seconds"]
                                               for r in mine))
        self.assertEqual((alpha["possessions_offense"], alpha["possessions_defense"]),
                         (100 * len(mine), 100 * len(against)))
        self.assertEqual(alpha["player_name"], "ALPHA, A")
        self.assertIsNone(pick(ROWS, "B0")["player_name"])

    def test_rows_are_sorted_rounded_and_match_the_registered_table(self):
        keys = [row["person_key"] for row in ROWS]
        self.assertEqual(keys, sorted(keys))
        self.assertEqual(set(ROWS[0]) | {"competition_code", "season_code"},
                         set(columns("player_rapm")))
        self.assertTrue(all(row["rapm"] == row["rapm"].quantize(Decimal("0.0001"))
                            for row in ROWS))
        self.assertIn("player_rapm", ROUND_NAMES)
        self.assertEqual(GOLD_TABLES["player_rapm"].key,
                         ("competition_code", "season_code", "scope", "person_key"))
        self.assertEqual({row["scope"] for row in ROWS}, {"all"})

    def test_a_missing_numpy_stops_only_this_table_with_a_clear_message(self):
        with patch.dict(sys.modules, {"numpy": None}):
            with self.assertRaisesRegex(ValueError, "gold.app_player_rapm needs numpy"):
                rapm.derive_rows(GAMES, STINTS, PLAYERS)
        self.assertEqual(rapm.derive_rows([], [], []), [])


class ReadAndStorageTests(unittest.TestCase):
    def test_read_rows_dispatches_through_the_shared_reader(self):
        from gold_etl.loader import read_aggregate_rows

        with patch.object(rapm, "read_silver", return_value=[GAMES, STINTS, PLAYERS]) as read:
            rows = read_aggregate_rows(object(), "player_rapm", "E", "E2025")
        self.assertEqual(rows, rapm.derive_rows(GAMES, STINTS, PLAYERS))
        self.assertEqual(read.call_args.args[3], ("game_team_lineup_stints",
                                                  "game_player_stats"))

    def test_replace_is_scoped_and_atomic(self):
        from gold_etl.loader import replace_aggregate_scope

        stored = dict(ROWS[0], competition_code="E", season_code="E2025")
        db = FakeConnection()
        with patch("gold_etl.loader.read_aggregate_rows", return_value=[stored]), \
                patch("psycopg2.extras.execute_values") as insert:
            self.assertEqual(replace_aggregate_scope(db, "player_rapm", "E", "E2025"), 1)
        self.assertEqual((db.commits, db.rollbacks), (1, 0))
        self.assertTrue(any(query.startswith('DELETE FROM gold."app_player_rapm"')
                            and params == ("E", "E2025") for query, params in db.queries))
        self.assertEqual(insert.call_args.args[2][0][:2], ("E", "E2025"))


if __name__ == "__main__":
    unittest.main()
