"""Minimum-games rule and played-round counting."""

import unittest

from gold_etl.qualification import min_games, scope_min_games, scope_rounds


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
