"""On-court event counts per player line: attribution, own events, possessions."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import on_court_rates
from test_lineups import GAME, LOCAL, PLAYERS, ROAD, SIMPLE, event


def counts(events, players=PLAYERS, game=GAME):
    return on_court_rates.derive_counts([game], players, events)


def local(result, person):
    return result[(1, "local", person)]


class CountTests(unittest.TestCase):
    def test_a_substitution_moves_later_events_to_the_new_lineup(self):
        result = counts(SIMPLE)
        a1, a2, a6 = (local(result, key) for key in ("a1", "a2", "a6"))
        # a1 scored the first basket, then left before road's basket and a2's three.
        self.assertEqual((a1["own"]["fga"], a1["own"]["fgm"], a1["own"]["two_pa"]), (1, 1, 1))
        self.assertEqual((a1["team"]["fga"], a1["opp"]["fga"]), (1, 0))
        self.assertEqual((a6["team"]["fga"], a6["opp"]["fga"], a6["opp"]["two_pa"]), (1, 1, 1))
        self.assertEqual((a6["own"]["fga"], a6["opp_possessions"]), (0, 1))
        self.assertEqual((a2["team"]["fga"], a2["own"]["fga"], a2["own"]["two_pa"]), (2, 1, 0))
        self.assertEqual(a1["opp_possessions"], 0)
        road = result[(1, "road", "b1")]
        self.assertEqual((road["own"]["fgm"], road["team"]["fga"], road["opp"]["fga"]), (1, 1, 2))

    def test_a_substitution_between_free_throws_splits_them(self):
        events = [event("FTM", "A", "05:00", 1, "a2", 1, 0),
                  event("OUT", "A", "05:00", 2, "a1"), event("IN", "A", "05:00", 3, "a6"),
                  event("FTM", "A", "05:00", 4, "a2", 2, 0)]
        result = counts(events)
        self.assertEqual(local(result, "a1")["team"]["fta"], 1)
        self.assertEqual(local(result, "a6")["team"]["fta"], 1)
        self.assertEqual((local(result, "a2")["team"]["fta"], local(result, "a2")["own"]["fta"]),
                         (2, 2))

    def test_a_team_rebound_counts_for_the_lineups_but_nobody_owns_it(self):
        result = counts([event("D", "A", "08:00", 1)])
        for person in LOCAL:
            self.assertEqual((local(result, person)["team"]["dreb"],
                              local(result, person)["own"]["dreb"]), (1, 0))
        for person in ROAD:
            self.assertEqual(result[(1, "road", person)]["opp"]["dreb"], 1)

    def test_blocked_attempts_are_field_goal_attempts_and_only_twos_count_for_blocks(self):
        result = counts([event("2FGAB", "B", "08:00", 1, "b1"), event("FV", "A", "08:00", 2, "a3"),
                         event("3FGAB", "B", "07:00", 3, "b2")])
        a3 = local(result, "a3")
        self.assertEqual((a3["opp"]["fga"], a3["opp"]["two_pa"], a3["own"]["blk"]), (2, 1, 1))

    def test_an_event_by_a_player_off_court_stays_with_the_team_only(self):
        events = [event("OUT", "A", "05:00", 1, "a1"), event("IN", "A", "05:00", 2, "a6"),
                  event("AS", "A", "04:00", 3, "a1"), event("2FGM", "A", "04:00", 4, "a2", 2, 0)]
        result = counts(events)
        self.assertEqual(local(result, "a1")["own"]["ast"], 0)
        self.assertEqual(local(result, "a6")["team"]["ast"], 1)

    def test_bench_players_get_zero_counts_and_games_without_events_none(self):
        bench = PLAYERS + [{"game_code": 1, "side": "local", "person_key": "a7",
                            "started": False}]
        a7 = local(counts([event("2FGM", "A", "09:00", 1, "a1", 2, 0)], players=bench), "a7")
        self.assertEqual((a7["team"]["fga"], a7["opp_possessions"]), (0, 0))
        self.assertEqual(counts([]), {})
        self.assertEqual(counts(SIMPLE, game=dict(GAME, played=False)), {})

    def test_a_side_without_starters_is_left_out(self):
        players = [p for p in PLAYERS if p["side"] == "local"]
        result = counts(SIMPLE, players=players)
        self.assertTrue(all(side == "local" for _, side, _ in result))


if __name__ == "__main__":
    unittest.main()
