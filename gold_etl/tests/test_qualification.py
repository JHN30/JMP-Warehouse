"""Minimum-games rule and played-round counting."""

import unittest

from gold_etl.qualification import (is_postseason, is_two_leg, min_games, postseason_phases,
                                    scope_min_games, scope_rounds)
from gold_etl.quality import check_postseason_phases
from gold_etl.team_rounds import _scopes


class Cursor:
    def __init__(self, pairs):
        self.pairs = pairs
        self.queries = []

    def execute(self, query, params=None):
        self.queries.append((query, params))

    def fetchall(self):
        return self.pairs


class MinGamesTests(unittest.TestCase):
    def test_more_than_half_of_the_rounds(self):
        cases = {("RS", 38): 20, ("RS", 34): 18, ("RS", 3): 2, ("RS", 1): 1,
                 ("PI", 2): 2, ("PO", 5): 3, ("all", 47): 24, ("all", 43): 22,
                 ("PS", 9): 5, ("RS", 0): 1}
        for (phase, rounds), expected in cases.items():
            with self.subTest(phase=phase, rounds=rounds):
                self.assertEqual(min_games(rounds, phase), expected)

    def test_final_four_is_never_filtered(self):
        self.assertEqual([min_games(rounds, "FF") for rounds in (0, 1, 2)], [1, 1, 1])

    def test_unknown_scope_falls_back_to_one_game(self):
        self.assertEqual(scope_min_games({"RS": 38}, "TS"), 1)
        self.assertEqual(scope_min_games({"RS": 38}, "RS"), 20)


class PostseasonPhaseTests(unittest.TestCase):
    def test_euroleague_phases_and_thresholds_are_unchanged(self):
        self.assertEqual(postseason_phases("E2025"), {"PI", "PO", "FF"})
        self.assertEqual(postseason_phases(None), {"PI", "PO", "FF"})
        self.assertEqual([min_games(5, "PO", "E2025"), min_games(2, "PI", "E2025"),
                          min_games(2, "FF", "E2025"), min_games(34, "RS", "E2025")], [3, 2, 1, 18])

    def test_eurocup_knockouts_by_season(self):
        self.assertEqual(postseason_phases("U2015"), {"8F", "4F", "2F", "Final"})
        self.assertTrue(is_postseason("L32", "U2007") and is_postseason("L16", "U2007"))
        self.assertFalse(is_postseason("L16", "U2008") or is_postseason("L32", "U2013"))
        self.assertFalse(is_postseason("RS", "U2007") or is_postseason("TS", "U2018"))

    def test_two_leg_table(self):
        two_leg = [("8F", "U2002"), ("Final", "U2002"), ("2F", "U2006"), ("L32", "U2007"),
                   ("4F", "U2010"), ("2F", "U2012"), ("Final", "U2015")]
        single_or_series = [("Final", "U2003"), ("4F", "U2007"), ("4F", "U2008"),
                            ("Final", "U2010"), ("Final", "U2012"), ("4F", "U2016"),
                            ("2F", "U2024"), ("8F", "U2026"), ("PO", "E2025")]
        self.assertTrue(all(is_two_leg(phase, season) for phase, season in two_leg))
        self.assertFalse(any(is_two_leg(phase, season) for phase, season in single_or_series))

    def test_eurocup_knockout_threshold_is_half_rounded_up(self):
        self.assertEqual([min_games(rounds, "4F", "U2018") for rounds in (1, 2, 3)], [1, 1, 2])
        self.assertEqual(min_games(10, "RS", "U2018"), 6)
        self.assertEqual(min_games(2, "L16", "U2008"), 2)  # a group stage
        self.assertEqual(scope_min_games({"Final": 2}, "Final", "U2024"), 1)

    def test_eurocup_ps_rounds_and_team_scopes(self):
        pairs = [("RS", 1), ("RS", 2), ("L32", 3), ("L16", 4), ("4F", 5), ("Final", 6)]
        self.assertEqual(scope_rounds(Cursor(pairs), "U", "U2007")["PS"], 4)
        self.assertEqual(scope_rounds(Cursor(pairs), "U", "U2013")["PS"], 2)
        self.assertEqual(list(_scopes("8F", "U2015")), ["all", "8F", "PS"])
        self.assertEqual(list(_scopes("L16", "U2008")), ["all", "L16"])
        self.assertEqual(list(_scopes("PO", "E2025")), ["all", "PO", "PS"])

    def test_unknown_eurocup_phase_is_a_warning(self):
        self.assertEqual(check_postseason_phases(Cursor([]), "E", "E2025"), [])
        cursor = Cursor([("PO", 3)])
        warnings = check_postseason_phases(cursor, "U", "U2026")
        self.assertEqual(len(warnings), 1)
        self.assertIn("U2026 PO: 3 played game(s)", warnings[0])
        self.assertIn("L16", cursor.queries[0][1][2])


class ScopeRoundsTests(unittest.TestCase):
    def test_phase_all_and_postseason_scopes(self):
        pairs = [("RS", 1), ("RS", 2), ("PI", 3), ("PO", 4), ("PO", 5), ("FF", 6)]
        rounds = scope_rounds(Cursor(pairs), "E", "E2025")
        self.assertEqual(rounds, {"RS": 2, "PI": 1, "PO": 2, "FF": 1, "all": 6, "PS": 4})

    def test_only_played_rounds_in_the_requested_scope_are_read(self):
        cursor = Cursor([])
        self.assertEqual(scope_rounds(cursor, "E", "E2026"), {})
        query, params = cursor.queries[0]
        self.assertIn("played IS TRUE", query)
        self.assertEqual(params, ("E", "E2026"))


if __name__ == "__main__":
    unittest.main()
