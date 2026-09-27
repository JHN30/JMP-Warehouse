import io
import json
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest import mock


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flat_schema import COLUMN_NAMES, TABLES, create_table_sql, physical_name
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

    def write(self, relative, value):
        self.store.write(relative.removesuffix(".json"), json.dumps(value).encode("utf-8"))

    def season(self):
        return FlatSeason(self.data_root, "euroleague", "E2025")

    def test_curated_tables_are_column_first(self):
        self.assertEqual(physical_name("games"), "games")
        for name, spec in TABLES.items():
            self.assertNotIn("payload", {field.name for field in spec.fields})
            json_columns = {field.name for field in spec.fields if field.kind.startswith("JSONB")}
            self.assertFalse(json_columns, name)
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
        rows = list(self.season().rows("season_player_stats_traditional"))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["two_pointers_percentage"], Decimal("45.5"))
        self.assertEqual(list(self.season().rows("season_player_stats_advanced")), [])
        self.assertNotIn("two_pointers_percentage", {
            field.name for field in TABLES["season_player_stats_advanced"].fields
        })

    def test_standings_form_is_a_child_table(self):
        rows = list(self.season().rows("standings_basic_form"))
        self.assertEqual([row["result"] for row in rows], ["W", "L"])

    def test_cli_flat_dry_run(self):
        self.assertEqual(main(["-sc", "2025", "-tb", "games", "game_period_scores",
                               "--data-root", str(self.data_root), "--dry-run"]), 0)

class CleanTableNameTests(unittest.TestCase):
    def test_silver_names_and_columns(self):
        self.assertEqual(len(TABLES), 28)
        self.assertEqual(physical_name("games"), "games")
        self.assertEqual(physical_name("standings_basic"), "standings_basic")
        self.assertEqual(physical_name("season_player_stats_misc"),
                         "season_player_stats_misc")
        for name, spec in TABLES.items():
            columns = {field.name for field in spec.fields}
            self.assertTrue(columns.isdisjoint(COLUMN_NAMES), name)
            self.assertEqual(spec.key[:2], ("competition_code", "season_code"))
            self.assertIn('"competition_code"', create_table_sql(name))

    def test_local_connection_uses_silver_search_path(self):
        from common.db import connect
        with tempfile.TemporaryDirectory() as root:
            config = Path(root) / "connection.json"
            config.write_text('{"dbname": "test"}', encoding="utf-8")
            connection = mock.MagicMock()
            with mock.patch("psycopg2.connect", return_value=connection):
                self.assertIs(connect(config), connection)
            connection.cursor.return_value.__enter__.return_value.execute.assert_called_once_with(
                'SET search_path TO silver')
            connection.commit.assert_called_once()

if __name__ == "__main__":
    unittest.main()
