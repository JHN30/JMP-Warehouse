"""Former postseason rules translated to typed Silver rows."""

import unittest
from decimal import Decimal

from gold_etl.postseason import COUNTING, derive_rows


def game(code, phase, local="MAD", road="BAR", played=True, local_score=80,
         road_score=70):
    return {"game_code": code, "phase_code": phase, "played": played,
            "scheduled_at": f"2025-05-{code:02d}",
            "local_club_code": local, "road_club_code": road,
            "local_score": local_score, "road_score": road_score}


def score(code, person="A", club="MAD", side="local", seconds=1500, **metrics):
    row = {metric: 0 for metric in COUNTING}
    row.update({"game_code": code, "person_key": person, "person_name": person,
                "club_code": club, "club_name": club, "side": side,
                "seconds_played": seconds, "started": False})
    row.update(metrics)
    return row


def by_person(result, table, mode):
    return {row["person_key"]: row for row in result[table]
            if row["mode"] == mode}


class PostseasonTests(unittest.TestCase):
    def test_played_pi_po_ff_only_and_latest_club(self):
        games = [game(1, "RS"), game(2, "PI"), game(3, "PO"), game(4, "FF"),
                 game(5, "FF", played=False)]
        scores = [score(1, points=100), score(2, points=10, started=True),
                  score(3, points=12, started=True),
                  score(4, club="BAR", side="road", points=13),
                  score(5, points=100)]
        rows = derive_rows(games, scores)
        traditional = by_person(rows, "season_player_stats_traditional", "accumulated")["A"]
        self.assertEqual((traditional["games_played"], traditional["games_started"],
                          traditional["points"]), (3, 2, Decimal(35)))
        self.assertEqual((traditional["phase_code"], traditional["club_code"]),
                         ("PS", "BAR"))
        self.assertEqual(traditional["minutes_played"], 75)
        self.assertEqual(traditional["entry_ordinal"], 0)
        self.assertEqual(set(rows), {"season_player_stats_traditional",
                                     "season_player_stats_misc"})

    def test_zero_minutes_missing_key_and_empty_postseason(self):
        games = [game(1, "PO")]
        scores = [score(1, seconds=0), score(1, person="", seconds=600),
                  score(1, person="unknown-0", seconds=600)]
        self.assertTrue(all(not rows for rows in derive_rows(games, scores).values()))
        self.assertTrue(all(not rows for rows in derive_rows([game(1, "RS")],
                                                               [score(1)]).values()))

    def test_missing_measure_propagates_and_percentages_use_totals(self):
        games = [game(1, "PI"), game(2, "PO")]
        scores = [score(1, points=12, two_pointers_made=2,
                        two_pointers_attempted=4, pir=None),
                  score(2, points=13, two_pointers_made=3,
                        two_pointers_attempted=6, pir=20)]
        rows = derive_rows(games, scores)
        acc = by_person(rows, "season_player_stats_traditional", "accumulated")["A"]
        per = by_person(rows, "season_player_stats_traditional", "perGame")["A"]
        self.assertEqual(acc["two_pointers_percentage"], Decimal("50.0"))
        self.assertEqual(per["two_pointers_percentage"], Decimal("50.0"))
        self.assertIsNone(acc["three_pointers_percentage"])
        self.assertIsNone(acc["pir"])
        self.assertIsNone(per["pir"])
        self.assertEqual(per["points"], Decimal("12.5"))

    def test_half_even_per_game_and_overtime_minutes(self):
        games = [game(code, "PO") for code in range(1, 5)]
        scores = [score(code, seconds=2700, points=points)
                  for code, points in enumerate((4, 4, 4, 5), 1)]
        rows = derive_rows(games, scores)
        acc = by_person(rows, "season_player_stats_traditional", "accumulated")["A"]
        per = by_person(rows, "season_player_stats_traditional", "perGame")["A"]
        self.assertEqual(acc["minutes_played"], 180)
        self.assertEqual(per["minutes_played"], 45)
        self.assertEqual(per["points"], Decimal("4.2"))

    def test_misc_wins_doubles_and_per_game_threshold(self):
        games = [game(1, "PI", local_score=80, road_score=70),
                 game(2, "PO", local_score=60, road_score=70),
                 game(3, "FF", local_score=90, road_score=80)]
        scores = [score(1, points=12, total_rebounds=11, assists=10),
                  score(2, points=9), score(3, points=10, assists=10),
                  score(1, person="C", seconds=600)]
        rows = derive_rows(games, scores)
        acc = by_person(rows, "season_player_stats_misc", "accumulated")["A"]
        per = by_person(rows, "season_player_stats_misc", "perGame")["A"]
        self.assertEqual((acc["wins"], acc["losses"], acc["double_doubles"],
                          acc["triple_doubles"]), (2, 1, 2, 1))
        for metric in ("wins", "losses", "double_doubles", "triple_doubles",
                       "minutes_played"):
            self.assertEqual(acc[metric], per[metric])
        self.assertIn("C", by_person(rows, "season_player_stats_misc", "accumulated"))
        self.assertNotIn("C", by_person(rows, "season_player_stats_misc", "perGame"))

    def test_identity_display_fields_and_stable_sort(self):
        games = [game(1, "PO")]
        scores = [score(1, person="B"), score(1, person="A")]
        rows = derive_rows(games, scores, {"A": {"player_age": 27,
                                                   "player_image_url": "a.png"}},
                           {"MAD": {"club_tv_codes": "RMB", "club_image_url": "mad.png"}})
        selected = [row for row in rows["season_player_stats_traditional"]
                    if row["mode"] == "accumulated"]
        self.assertEqual([(row["person_key"], row["entry_ordinal"]) for row in selected],
                         [("A", 0), ("B", 1)])
        self.assertEqual((selected[0]["player_age"], selected[0]["club_tv_codes"]),
                         (27, "RMB"))
        self.assertIsNone(selected[1]["player_age"])


if __name__ == "__main__":
    unittest.main()
