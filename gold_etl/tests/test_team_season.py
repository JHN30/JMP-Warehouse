"""Team-season totals and the historical output schema."""

import unittest
from decimal import Decimal

from gold_etl.schema import TEAM_MEASURE_COLUMNS, TEAM_SEASON_TABLE, columns
from gold_etl.team_season import derive_rows


def game(code, phase="RS", played=True):
    return {"game_code": code, "phase_code": phase, "played": played,
            "local_club_code": "MAD", "road_club_code": "BAR",
            "local_club_name": "Madrid game", "road_club_name": "Barcelona game"}


def stats(code, side, points, **metrics):
    return {"game_code": code, "side": side, "stats_kind": "total",
            "points": points, **{source: metrics.get(source, 1)
                                 for _, source in TEAM_MEASURE_COLUMNS if source != "points"}}


class TeamSeasonTests(unittest.TestCase):
    def test_historical_key_and_twenty_measure_pairs(self):
        self.assertEqual(TEAM_SEASON_TABLE.key,
                         ("competition_code", "season_code", "phase_code", "club_code"))
        self.assertEqual(len(TEAM_MEASURE_COLUMNS), 20)
        self.assertIn("own_field_goals_made2", columns("app_team_season_stats"))
        self.assertIn("opp_fouls_commited", columns("app_team_season_stats"))

    def test_sides_phases_club_name_and_nulls(self):
        games = [game(1), game(2), game(3, "TS"), game(4, played=False)]
        boxes = [stats(1, "local", 10), stats(1, "road", 8),
                 stats(2, "local", None), stats(2, "road", 6),
                 stats(3, "local", 7), stats(3, "road", 9),
                 stats(4, "local", 100), stats(4, "road", 100)]
        rows = derive_rows(games, boxes, [{"club_code": "MAD", "name": "Madrid"}])
        self.assertEqual(len(rows), 4)
        madrid = next(row for row in rows if row["club_code"] == "MAD" and
                      row["phase_code"] == "RS")
        self.assertEqual((madrid["club_name"], madrid["games_played"]), ("Madrid", 2))
        self.assertIsNone(madrid["own_points"])
        self.assertEqual(madrid["opp_points"], Decimal(14))
        self.assertEqual(madrid["own_assistances"], Decimal(2))
        barcelona = next(row for row in rows if row["club_code"] == "BAR" and
                         row["phase_code"] == "RS")
        self.assertEqual(barcelona["club_name"], "Barcelona game")
        self.assertIsNone(barcelona["opp_points"])
        self.assertEqual(sum(row["phase_code"] == "TS" for row in rows), 2)

    def test_missing_box_score_and_opponent_stay_unavailable(self):
        rows = derive_rows([game(1), game(2)],
                           [stats(1, "local", 10), stats(1, "road", 8),
                            stats(2, "local", 12)], [])
        madrid = next(row for row in rows if row["club_code"] == "MAD")
        self.assertEqual((madrid["games_played"], madrid["own_points"]),
                         (2, Decimal(22)))
        self.assertIsNone(madrid["opp_points"])
        self.assertEqual(next(row for row in rows if row["club_code"] == "BAR")
                         ["games_played"], 1)
        self.assertEqual(derive_rows([game(3)], [], []), [])

    def test_forfeit_without_box_score_is_not_counted(self):
        empty = {source: None for _, source in TEAM_MEASURE_COLUMNS if source != "points"}
        boxes = [stats(1, "local", 80), stats(1, "road", 70),
                 stats(2, "local", None, **empty), stats(2, "road", None, **empty)]
        rows = derive_rows([game(1), game(2)], boxes, [], no_box_score=[2])
        for club, own, opp in (("MAD", 80, 70), ("BAR", 70, 80)):
            row = next(row for row in rows if row["club_code"] == club)
            self.assertEqual(row["games_played"], 1)
            self.assertEqual((row["own_points"], row["opp_points"]),
                             (Decimal(own), Decimal(opp)))
            self.assertTrue(all(row[f"{side}_{target}"] is not None
                                for target, _ in TEAM_MEASURE_COLUMNS
                                for side in ("own", "opp")))
        counted = derive_rows([game(1), game(2)], boxes, [])
        self.assertIsNone(next(row for row in counted
                               if row["club_code"] == "MAD")["own_points"])


if __name__ == "__main__":
    unittest.main()
