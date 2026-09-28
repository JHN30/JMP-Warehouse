"""Season and per-game coverage contracts over Silver identifiers."""

import unittest

from gold_etl.coverage import ITEMS, derive_rows, item
from gold_etl.schema import COVERAGE_GAME_TABLE, COVERAGE_SEASON_TABLE, create_table_sql


def coverage(games, clubs=(), box=(), period=(), standings=(), rosters=(),
             photos=(), stats=(), shots=(), play=()):
    return derive_rows(games, set(clubs), set(box), set(period), set(standings),
                       set(rosters), set(photos), set(stats), set(shots), set(play))


class CoverageTests(unittest.TestCase):
    def test_keys_json_and_historical_labels(self):
        self.assertEqual(COVERAGE_SEASON_TABLE.key, ("competition_code", "season_code"))
        self.assertEqual(COVERAGE_GAME_TABLE.key,
                         ("competition_code", "season_code", "game_code"))
        self.assertIn('"items" JSONB NOT NULL', create_table_sql("app_coverage_games"))
        self.assertEqual([key for key, _ in ITEMS],
                         ["boxScores", "periodScores", "officialStandings", "rosters",
                          "playerPhotos", "seasonStatistics", "shotLocations", "playByPlay"])
        self.assertEqual(dict(ITEMS)["playByPlay"], "Play-by-play")

    def test_empty_and_status_boundaries(self):
        result = coverage([])
        self.assertEqual(len(result["app_coverage_seasons"]), 1)
        self.assertEqual(result["app_coverage_games"], [])
        self.assertTrue(all(value["status"] == "notYetApplicable"
                            for value in result["app_coverage_seasons"][0]["items"]))
        self.assertEqual(item("boxScores", 0, 2)["status"], "unavailable")
        self.assertEqual(item("boxScores", 1, 2)["status"], "partial")
        self.assertEqual(item("rosters", 1, 2)["status"], "incomplete")
        self.assertEqual(item("playerPhotos", 3, 2)["status"], "available")

    def test_distinct_counts_and_per_game_scope(self):
        games = [{"game_code": 1, "played": True},
                 {"game_code": 2, "played": True},
                 {"game_code": 3, "played": False}]
        rows = coverage(games, clubs=("MAD", "BAR"), box=(1, 3),
                        period=(1, 2), standings=("MAD",), rosters=("BAR",),
                        photos=((1, "p1"), (1, "p2"), (2, "p1"), (3, "p3")),
                        stats=("p1", "p2"), shots=(2, 3), play=(1,))
        season = {x["key"]: x for x in rows["app_coverage_seasons"][0]["items"]}
        self.assertEqual((season["boxScores"]["availableCount"],
                          season["boxScores"]["applicableCount"]), (1, 2))
        self.assertEqual(season["playerPhotos"]["availableCount"], 2)
        self.assertEqual(season["playerPhotos"]["status"], "available")
        self.assertEqual(season["officialStandings"]["status"], "incomplete")
        self.assertEqual(season["seasonStatistics"]["availableCount"], 2)
        self.assertEqual(season["shotLocations"]["availableCount"], 1)
        self.assertEqual(season["playByPlay"]["availableCount"], 1)
        games_by_id = {row["game_code"]: {x["key"]: x for x in row["items"]}
                       for row in rows["app_coverage_games"]}
        self.assertEqual(games_by_id[1]["playerPhotos"]["availableCount"], 2)
        self.assertEqual(games_by_id[2]["playerPhotos"]["availableCount"], 1)
        self.assertEqual(games_by_id[3]["boxScores"]["status"], "notYetApplicable")
        self.assertEqual(games_by_id[3]["shotLocations"]["availableCount"], 0)
        for game_items in games_by_id.values():
            for key in ("officialStandings", "rosters", "seasonStatistics"):
                self.assertEqual(game_items[key], season[key])


if __name__ == "__main__":
    unittest.main()
