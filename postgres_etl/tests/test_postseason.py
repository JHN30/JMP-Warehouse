import sys
import unittest
from decimal import Decimal
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from postseason import postseason_payloads


def game(code, phase, local, road, local_score, road_score, played=True, day=None):
    return {"gameCode": code, "played": played, "phaseType": {"code": phase},
            "utcDate": f"2026-05-{day or code:02d}T18:00:00Z",
            "local": {"club": {"code": local}, "score": local_score},
            "road": {"club": {"code": road}, "score": road_score}}


def player(code, club, seconds, started=False, **stats):
    values = {"timePlayed": seconds, "startFive": started, "points": 0,
              "fieldGoalsMade2": 0, "fieldGoalsAttempted2": 0, "fieldGoalsMade3": 0,
              "fieldGoalsAttempted3": 0, "freeThrowsMade": 0, "freeThrowsAttempted": 0,
              "offensiveRebounds": 0, "defensiveRebounds": 0, "totalRebounds": 0,
              "assistances": 0, "steals": 0, "turnovers": 0, "blocksFavour": 0,
              "blocksAgainst": 0, "foulsCommited": 0, "foulsReceived": 0, "valuation": 0}
    values.update(stats)
    return {"player": {"person": {"code": code, "name": f"PLAYER {code}"},
                       "club": {"code": club, "name": f"Club {club}"}},
            "stats": values}


def box(local_players, road_players):
    return {"local": {"players": local_players}, "road": {"players": road_players}}


class PostseasonTests(unittest.TestCase):
    def setUp(self):
        self.games = [
            game(1, "RS", "MAD", "BAR", 80, 70),
            game(2, "PO", "MAD", "BAR", 90, 80),
            game(3, "PO", "BAR", "MAD", 85, 75),
            game(4, "FF", "MAD", "OLY", 70, 72),
            game(5, "FF", "MAD", "OLY", 0, 0, played=False),
        ]
        self.box_scores = {
            1: box([player("A", "MAD", 1200, points=50)], []),
            2: box([player("A", "MAD", 1800, True, points=20, totalRebounds=12,
                           fieldGoalsMade2=7, fieldGoalsAttempted2=10,
                           freeThrowsMade=1, freeThrowsAttempted=3, valuation=25),
                    player("C", "MAD", 0)],
                   [player("B", "BAR", 600, points=3)]),
            3: box([player("B", "BAR", 1500, points=4)],
                   [player("A", "MAD", 1500, True, points=10, totalRebounds=10,
                           assistances=10, fieldGoalsMade2=3, fieldGoalsAttempted2=10),
                    player("C", "MAD", 300, points=2)]),
            4: box([player("A", "MAD", 1200, points=5, fieldGoalsMade2=2,
                           fieldGoalsAttempted2=5, valuation=None)],
                   [player("D", "OLY", 900, points=9)]),
        }
        self.identities = {"A": {"age": 27, "imageUrl": "a.png"}}
        self.clubs = {"MAD": {"tvCodes": "RMB", "imageUrl": "mad.png"}}

    def rows(self):
        return postseason_payloads(self.games, self.box_scores, self.identities, self.clubs)

    def by_code(self, category, mode):
        return {row["player"]["code"]: row for row in self.rows()[(category, mode)]}

    def test_totals_come_from_played_postseason_games_with_minutes(self):
        a = self.by_code("traditional", "accumulated")["A"]
        self.assertEqual((a["gamesPlayed"], a["gamesStarted"]), (3, 2))
        self.assertEqual(a["pointsScored"], 35)  # RS game 1 and unplayed game 5 ignored
        self.assertEqual(a["minutesPlayed"], 75)
        self.assertEqual((a["twoPointersMade"], a["twoPointersAttempted"]), (12, 25))

    def test_did_not_play_rows_are_not_players(self):
        players = set(self.by_code("traditional", "accumulated"))
        self.assertEqual(players, {"A", "B", "C", "D"})
        self.assertEqual(self.by_code("traditional", "accumulated")["C"]["gamesPlayed"], 1)

    def test_percentages_use_totals_and_zero_attempts_are_null(self):
        a = self.by_code("traditional", "accumulated")["A"]
        self.assertEqual(a["twoPointersPercentage"], Decimal("48.0"))
        self.assertEqual(a["freeThrowsPercentage"], Decimal("33.3"))
        self.assertIsNone(a["threePointersPercentage"])
        per_game = self.by_code("traditional", "perGame")["A"]
        self.assertEqual(per_game["twoPointersPercentage"], Decimal("48.0"))

    def test_per_game_values_round_half_to_even_and_minutes_are_exact(self):
        a = self.by_code("traditional", "perGame")["A"]
        self.assertEqual(a["gamesPlayed"], 3)
        self.assertEqual(a["minutesPlayed"], 25)
        self.assertEqual(a["totalRebounds"], Decimal("7.3"))
        # 17 points in 4 games: 4.25 rounds to 4.2, as the API does.
        games = [game(9 + n, "PO", "MAD", "BAR", 1, 0) for n in range(4)]
        scores = {9 + n: box([player("A", "MAD", 60, points=points)], [])
                  for n, points in enumerate((5, 4, 4, 4))}
        rows = postseason_payloads(games, scores)
        self.assertEqual(rows[("traditional", "perGame")][0]["pointsScored"], Decimal("4.2"))

    def test_an_unrecorded_measure_in_any_game_makes_the_total_null(self):
        a = self.by_code("traditional", "accumulated")["A"]
        self.assertIsNone(a["pir"])
        self.assertIsNone(self.by_code("traditional", "perGame")["A"]["pir"])

    def test_misc_counts_wins_losses_and_doubles_the_same_in_both_modes(self):
        accumulated = self.by_code("misc", "accumulated")["A"]
        self.assertEqual((accumulated["wins"], accumulated["losses"]), (1, 2))
        self.assertEqual((accumulated["doubleDoubles"], accumulated["tripleDoubles"]), (2, 1))
        self.assertEqual(accumulated["minutesPlayed"], 25)
        self.assertEqual(self.by_code("misc", "perGame")["A"], accumulated)

    def test_per_game_rows_need_more_than_half_of_the_clubs_games(self):
        # MAD played 3 postseason games: C (1 game) is only in accumulated.
        # OLY played 1: D (1 of 1) qualifies. BAR played 2: B (2 of 2) qualifies.
        self.assertEqual(set(self.by_code("traditional", "perGame")), {"A", "B", "D"})
        self.assertEqual(set(self.by_code("misc", "perGame")), {"A", "B", "D"})
        self.assertIn("C", self.by_code("misc", "accumulated"))

    def test_identity_uses_latest_box_score_and_season_api_rows(self):
        a = self.by_code("traditional", "accumulated")["A"]["player"]
        self.assertEqual(a, {"code": "A", "name": "PLAYER A", "age": 27, "imageUrl": "a.png",
                             "team": {"code": "MAD", "name": "Club MAD", "tvCodes": "RMB",
                                      "imageUrl": "mad.png"}})
        d = self.by_code("traditional", "accumulated")["D"]["player"]
        self.assertIsNone(d["age"])
        self.assertIsNone(d["team"]["tvCodes"])

    def test_rows_are_sorted_like_the_api_feeds(self):
        rows = self.rows()
        self.assertEqual([row["player"]["code"] for row in rows[("traditional", "accumulated")]],
                         ["A", "B", "D", "C"])
        self.assertEqual([row["player"]["code"] for row in rows[("misc", "accumulated")]],
                         ["A", "B", "D", "C"])

    def test_no_postseason_games_means_no_rows(self):
        self.assertEqual(postseason_payloads([game(1, "RS", "MAD", "BAR", 80, 70)],
                                             self.box_scores), {})


if __name__ == "__main__":
    unittest.main()
