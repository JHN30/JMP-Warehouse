import json
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flat_schema import (PUBLISHED_TABLES, TABLES, create_table_sql, legacy_name, physical_name,
                         rename_actions)
from flat_transform import FlatSeason
from main import main
from shared import BronzeStore


class FlatEtlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data_root = Path(self.temp.name)
        self.store = BronzeStore(self.data_root / "bronze", "euroleague", "E2025")
        self.write("v2/games.json", {"data": [
            {"gameCode": 1, "played": True, "utcDate": "2025-10-01T18:00:00Z",
             "local": {"club": {"code": "MAD"}, "score": 85,
                       "partials": {"partials1": 20, "extraPeriods": {"1": 8}}},
             "road": {"club": {"code": "BAR"}, "score": 80,
                      "partials": {"partials1": 15, "extraPeriods": {"1": 5}}},
             "winner": {"code": "OLY"}},
            {"gameCode": 2, "played": False, "utcDate": "2026-04-01T18:00:00Z",
             "local": {"club": {"code": "MAD"}, "score": 0,
                       "partials": {"partials1": 0, "extraPeriods": {}}},
             "road": {"club": {"code": "OLY"}, "score": 0,
                      "partials": {"partials1": 0, "extraPeriods": {}}}}
        ]})
        self.write("v3/season_stats/players_traditional_RS_perGame.json", {
            "players": [{"player": {"code": "000123", "name": "Test",
                                    "team": {"code": "MAD"}},
                         "gamesPlayed": 1, "twoPointersPercentage": "45.5%", "pointsScored": 10}]
        })
        self.write("v3/standings/RS_1_basicstandings.json", {
            "teams": [{"club": {"code": "MAD"}, "position": 1,
                       "gamesPlayed": 1, "last5Form": ["W", "L"]}]
        })
        self.write("live/1/live_boxscores.json", {
            "Attendance": "1000", "Stats": [],
            "ByQuarter": [{"Team": "MAD", "Quarter1": 20, "Extra1": 8},
                          {"Team": "BAR", "Quarter1": 15, "Extra1": 5}],
            "EndOfQuarter": []
        })
        self.write("live/1/live_evolution.json", {
            "MinutesList": [0, 1], "PointsList": [[2, 4], [0, 2]],
            "ScoreDiffPerMinute": [[2, 2], [None, None]],
            "LargestDifference": [[3, None], [None, 1]]
        })

    def write(self, relative, value):
        self.store.write(relative.removesuffix(".json"), json.dumps(value).encode("utf-8"))

    def season(self):
        return FlatSeason(self.data_root, "euroleague", "E2025")

    def test_curated_tables_are_column_first(self):
        self.assertEqual(physical_name("games"), "app_games")
        for name, spec in TABLES.items():
            if name == "source_payloads":
                continue
            self.assertNotIn("payload", {field.name for field in spec.fields})
            json_columns = {field.name for field in spec.fields if field.kind.startswith("JSONB")}
            # Page-shaped app tables may carry the lists their API returns.
            allowed = {"form", "streak_history", "items"} if name.startswith("app_") else set()
            self.assertLessEqual(json_columns, allowed, name)
        self.assertNotIn("extra_1", create_table_sql("games"))

    def test_future_placeholders_are_not_results(self):
        games = list(self.season().rows("games"))
        self.assertEqual(len(games), 2)
        self.assertEqual(games[0]["match_winner_club_code"], "MAD")
        self.assertEqual(games[0]["champion_club_code"], "OLY")
        self.assertIsNone(games[1]["local_score"])
        self.assertIsNone(games[1]["road_score"])
        self.assertIsNone(games[1]["match_winner_club_code"])

    def test_overtime_is_a_child_row_not_a_null_column(self):
        periods = list(self.season().rows("game_period_scores"))
        self.assertEqual(len(periods), 4)
        self.assertEqual({row["game_code"] for row in periods}, {1})
        overtime = [row for row in periods if row["period_number"] == 5]
        self.assertEqual({row["score"] for row in overtime}, {8, 5})

    def test_categories_and_percentages(self):
        rows = list(self.season().rows("season_stats_traditional"))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["two_pointers_percentage"], Decimal("45.5"))
        self.assertEqual(list(self.season().rows("season_stats_advanced")), [])
        self.assertNotIn("two_pointers_percentage", {
            field.name for field in TABLES["season_stats_advanced"].fields
        })

    def test_standings_form_is_a_child_table(self):
        rows = list(self.season().rows("standings_basic_form"))
        self.assertEqual([row["result"] for row in rows], ["W", "L"])

    def test_live_nested_lists_become_period_and_minute_rows(self):
        periods = list(self.season().rows("live_boxscore_period_scores"))
        self.assertEqual(len(periods), 4)
        self.assertEqual({row["period_number"] for row in periods}, {1, 5})
        minutes = list(self.season().rows("live_evolution_minutes"))
        self.assertEqual([row["score_difference"] for row in minutes], [2, 2])
        differences = list(self.season().rows("live_evolution_largest_differences"))
        self.assertEqual([row["difference"] for row in differences], [Decimal(3), Decimal(1)])

    def test_cli_flat_dry_run(self):
        self.assertEqual(main(["-sc", "2025", "-tb", "games", "game_period_scores",
                               "--data-root", str(self.data_root), "--dry-run"]), 0)



class CleanTableNameTests(unittest.TestCase):
    def test_published_tables_have_app_names_and_the_rest_keep_theirs(self):
        self.assertEqual(len(PUBLISHED_TABLES), 30)
        self.assertEqual(physical_name("standings_basicstandings"), "app_standings_basicstandings")
        self.assertEqual(legacy_name("games"), "etl_flat_games")
        self.assertEqual(physical_name("play_by_play"), "app_play_by_play")
        self.assertEqual(legacy_name("shots"), "etl_flat_shots")
        self.assertEqual(physical_name("live_boxscores"), "etl_flat_live_boxscores")
        self.assertIsNone(legacy_name("live_boxscores"))
        self.assertEqual(physical_name("app_standings"), "app_standings")
        self.assertIsNone(legacy_name("app_standings"))
        self.assertEqual(physical_name("source_payloads"), "etl_source_payloads")
        self.assertTrue(all(physical_name(name).startswith("app_") for name in PUBLISHED_TABLES))

    def test_legacy_table_is_renamed_and_optionally_kept_as_a_view(self):
        kinds = {"etl_flat_games": "table"}
        self.assertEqual(rename_actions(kinds, ["games"]),
                         [("rename", "etl_flat_games", "app_games")])
        self.assertEqual(rename_actions(kinds, ["games"], keep_views=True),
                         [("rename", "etl_flat_games", "app_games"),
                          ("view", "etl_flat_games", "app_games")])

    def test_already_renamed_missing_or_unrenamed_tables_need_nothing(self):
        for kinds in ({"app_games": "table", "etl_flat_games": "view"},  # renamed, view kept
                      {"app_games": "table"},                            # renamed, view dropped
                      {}):                                               # created fresh later
            for keep_views in (False, True):
                self.assertEqual(rename_actions(kinds, ["games"], keep_views), [])
        self.assertEqual(rename_actions({"etl_flat_live_boxscores": "table"},
                                        ["live_boxscores", "app_standings"], True), [])

    def test_old_and_new_tables_side_by_side_are_refused(self):
        with self.assertRaisesRegex(ValueError, "Both etl_flat_games and app_games"):
            rename_actions({"etl_flat_games": "table", "app_games": "table"}, ["games"])
        with self.assertRaisesRegex(ValueError, "app_games exists but is not a table"):
            rename_actions({"etl_flat_games": "table", "app_games": "view"}, ["games"])


if __name__ == "__main__":
    unittest.main()
