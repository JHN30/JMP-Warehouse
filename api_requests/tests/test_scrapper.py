from argparse import Namespace
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


API_REQUESTS_DIRECTORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_REQUESTS_DIRECTORY))

from scrapper import EuroScrapas
from utils import ConfigParser
from common.bronze import BronzeStore  # project root is put on sys.path by scrapper


def reply(payload, url):
    return payload, 200, url, json.dumps(payload).encode("utf-8")


class FakeClient:
    def __init__(self, games):
        self.games = games
        self.calls = []

    def get_json(self, url, params=None):
        self.calls.append((url, params))
        if url.endswith("/games"):
            return reply({"data": self.games}, url)
        if url.endswith("/stats"):
            return reply({"local": {}, "road": {}}, url)
        return reply({"Rows": []}, url)


class PaginatedPeopleClient(FakeClient):
    def __init__(self, games, people):
        super().__init__(games)
        self.people = people

    def get_json(self, url, params=None):
        self.calls.append((url, params))
        if url.endswith("/games"):
            return reply({"data": self.games}, url)
        if url.endswith("/people"):
            offset = params["offset"]
            limit = params["limit"]
            return reply({
                "data": self.people[offset:offset + limit],
                "total": len(self.people),
            }, url)
        return reply({"Rows": []}, url)


class EuroScrapasTests(unittest.TestCase):
    def make_scrapper(
        self,
        root,
        datasets,
        season_code="E2026",
        year=2026,
        live_apis=None,
    ):
        scrapper = EuroScrapas(
            competition="euroleague",
            season_codes=[season_code],
            datasets=datasets,
            euroleague_apis=live_apis or ["Boxscore", "Points"],
            failed_extractions_limit=500,
            game_code_start=1,
            datetime_now="test",
            year_today=year,
            refresh_current=False,
            request_interval=0,
        )
        scrapper.bronze_root = root / "bronze"
        return scrapper

    @staticmethod
    def stored(root, season_code, resource):
        return BronzeStore(root / "bronze", "euroleague", season_code).exists(resource)

    def test_future_games_are_cached_but_detail_is_only_fetched_for_played_games(self):
        games = [
            {"gameCode": 1, "played": True, "round": 1, "phaseType": {"code": "RS"}},
            {"gameCode": 2, "played": False, "round": 2, "phaseType": {"code": "RS"}},
        ]

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            scrapper = self.make_scrapper(
                root,
                {"game_lists", "game_stats", "live_boxscores", "shooting_charts"},
            )
            fake_client = FakeClient(games)
            scrapper.client = fake_client

            scrapper.extract_season("E2026")

            store = BronzeStore(root / "bronze", "euroleague", "E2026")
            self.assertEqual(store.read_json("v2/games")["data"], games)
            self.assertTrue(self.stored(root, "E2026", "v2/game_stats/1"))
            self.assertFalse(self.stored(root, "E2026", "v2/game_stats/2"))
            self.assertTrue(self.stored(root, "E2026", "live/1/live_boxscores"))
            self.assertFalse(self.stored(root, "E2026", "live/2/live_boxscores"))

    def test_bronze_keeps_exact_bytes_and_only_new_versions(self):
        games = [{"gameCode": 1, "played": False, "round": 1, "phaseType": {"code": "RS"}}]

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            scrapper = self.make_scrapper(root, {"game_lists"})
            fake_client = FakeClient(games)
            scrapper.client = fake_client
            store = BronzeStore(root / "bronze", "euroleague", "E2026")

            scrapper.extract_season("E2026")
            scrapper.extract_season("E2026")
            self.assertEqual(len(store.versions("v2/games")), 1)
            self.assertEqual(store.read_bytes("v2/games"),
                             json.dumps({"data": games}).encode("utf-8"))

            fake_client.games = [dict(games[0], played=True)]
            scrapper.extract_season("E2026")
            self.assertEqual(len(store.versions("v2/games")), 2)
            manifest = [json.loads(line) for line in
                        (store.directory / "manifest.jsonl").read_text().splitlines()]
            self.assertEqual([entry["stored_as"] is not None for entry in manifest
                              if entry["resource"] == "v2/games"], [True, False, True])
            self.assertTrue(all(entry["status_code"] == 200 and len(entry["sha256"]) == 64
                                for entry in manifest))

    def test_current_game_list_refreshes_but_cached_game_detail_does_not(self):
        games = [
            {"gameCode": 1, "played": True, "round": 1, "phaseType": {"code": "RS"}},
        ]

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            scrapper = self.make_scrapper(
                root,
                {"game_lists", "game_stats", "live_boxscores"},
            )
            fake_client = FakeClient(games)
            scrapper.client = fake_client

            scrapper.extract_season("E2026")
            scrapper.extract_season("E2026")

            game_list_calls = [
                call for call in fake_client.calls if call[0].endswith("/games")
            ]
            game_stat_calls = [
                call for call in fake_client.calls if call[0].endswith("/stats")
            ]
            live_boxscore_calls = [
                call for call in fake_client.calls if call[0].endswith("/Boxscore")
            ]
            self.assertEqual(len(game_list_calls), 2)
            self.assertEqual(len(game_stat_calls), 1)
            self.assertEqual(len(live_boxscore_calls), 1)

    def test_live_detail_is_not_requested_before_2007(self):
        games = [
            {"gameCode": 1, "played": True, "round": 1, "phaseType": {"code": "RS"}},
        ]

        with tempfile.TemporaryDirectory() as temporary_directory:
            scrapper = self.make_scrapper(
                Path(temporary_directory),
                {"game_lists", "live_boxscores"},
                season_code="E2006",
                year=2006,
            )
            fake_client = FakeClient(games)
            scrapper.client = fake_client

            scrapper.extract_season("E2006")

            self.assertFalse(
                any(call[0].endswith("/Boxscore") for call in fake_client.calls)
            )

    def test_play_by_play_uses_the_verified_canonical_endpoint_name(self):
        games = [
            {"gameCode": 1, "played": True, "round": 1, "phaseType": {"code": "RS"}},
        ]

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            scrapper = self.make_scrapper(
                root,
                {"game_lists", "play_by_play"},
                live_apis=["PlayByPlay"],
            )
            fake_client = FakeClient(games)
            scrapper.client = fake_client

            scrapper.extract_season("E2026")

            self.assertTrue(
                any(call[0].endswith("/PlayByPlay") for call in fake_client.calls)
            )
            self.assertTrue(self.stored(root, "E2026", "live/1/play_by_play"))

    def test_incomplete_season_people_cache_is_backfilled_with_all_pages(self):
        games = [
            {"gameCode": 1, "played": True, "round": 1, "phaseType": {"code": "RS"}},
        ]
        people = [{"person": {"code": str(index)}} for index in range(5)]

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            scrapper = self.make_scrapper(
                root,
                {"game_lists", "season_people"},
                season_code="E2025",
                year=2026,
            )
            scrapper.V2_PEOPLE_PAGE_SIZE = 2
            store = BronzeStore(root / "bronze", "euroleague", "E2025")
            # Only the first page is cached: the pages are incomplete.
            store.write("v2/season_people_pages/offset_000000",
                        json.dumps({"data": people[:2], "total": len(people)}).encode())
            fake_client = PaginatedPeopleClient(games, people)
            scrapper.client = fake_client

            scrapper.extract_season("E2025")

            people_offsets = [
                call[1]["offset"]
                for call in fake_client.calls
                if call[0].endswith("/people")
            ]
            self.assertEqual(people_offsets, [0, 2, 4])
            rows = [row for page in scrapper.cached_people_pages() for row in page["data"]]
            self.assertEqual(rows, people)
            self.assertTrue(self.stored(root, "E2025", "v2/season_people_pages/offset_000004"))

            fake_client.calls.clear()
            scrapper.extract_season("E2025")
            self.assertFalse(
                any(call[0].endswith("/people") for call in fake_client.calls)
            )

    def test_legacy_playbyplay_cli_spelling_is_normalized(self):
        parser = ConfigParser(year_today=2026)
        args = Namespace(
            competition="euroleague",
            season_code=["2025"],
            dataset=["play_by_play"],
            euroleague_api=["PlaybyPlay"],
            failed_extractions_limit=500,
            game_code_start=1,
            refresh_current=False,
            request_interval=0,
        )

        parser.parse_arguments(args)

        self.assertEqual(parser.euroleague_apis, ["PlayByPlay"])

    def test_default_datasets_skip_redundant_live_endpoints_unless_named(self):
        def parse(datasets):
            parser = ConfigParser(year_today=2026)
            parser.parse_arguments(Namespace(
                competition="euroleague", season_code=["2025"], dataset=datasets,
                euroleague_api=list(EuroScrapas.LIVE_DATASETS.values()),
                failed_extractions_limit=500, game_code_start=1,
                refresh_current=False, request_interval=0,
            ))
            return parser.datasets

        defaults = parse(["all"])
        self.assertIn("play_by_play", defaults)
        self.assertIn("shooting_charts", defaults)
        for redundant in ("live_boxscores", "live_evolution", "live_comparison", "live_scoring"):
            self.assertNotIn(redundant, defaults)
        self.assertIn("live_boxscores", parse(["all", "live_boxscores"]))

    def test_time_counter_shows_season_and_total_time(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            scrapper = self.make_scrapper(Path(temporary_directory), {"game_lists"})
            with patch("scrapper.monotonic", return_value=1000.0):
                scrapper.run_started_at = 1000.0 - 70 * 60   # run started 70 minutes ago
                scrapper.season_started_at = 1000.0 - 30 * 60  # this season 30 minutes ago
                self.assertEqual(scrapper.get_time_counter(),
                                 "TimeCounter: 30.0 min  ---  TotalTime: 70.0 min")

    def test_run_summary_lists_only_the_live_endpoints_that_are_called(self):
        parser = ConfigParser(year_today=2026)
        parser.parse_arguments(Namespace(
            competition="euroleague", season_code=["2000-2025"], dataset=["all"],
            euroleague_api=list(EuroScrapas.LIVE_DATASETS.values()),
            failed_extractions_limit=500, game_code_start=1,
            refresh_current=False, request_interval=2.5,
        ))
        summary = "\n".join(parser.describe())
        self.assertEqual(parser.live_endpoints, ["PlayByPlay", "Points"])
        self.assertIn("seasons: E2000-E2025 (26 seasons)", summary)
        for unused in ("Boxscore", "Evolution", "Comparison", "ShootingGraphic", "current season"):
            self.assertNotIn(unused, summary)

    def test_standings_are_requested_for_group_rounds_only(self):
        games = [
            {
                "gameCode": 1,
                "played": True,
                "round": 1,
                "phaseType": {"code": "RS", "isGroupPhase": True},
            },
            {
                "gameCode": 2,
                "played": True,
                "round": 46,
                "phaseType": {"code": "FF", "isGroupPhase": False},
            },
        ]

        with tempfile.TemporaryDirectory() as temporary_directory:
            scrapper = self.make_scrapper(
                Path(temporary_directory),
                {"game_lists", "standings"},
            )
            fake_client = FakeClient(games)
            scrapper.client = fake_client

            scrapper.extract_season("E2026")

            standing_urls = [
                call[0] for call in fake_client.calls if "/basicstandings" in call[0]
            ]
            self.assertEqual(len(standing_urls), 1)
            self.assertIn("/rounds/1/", standing_urls[0])
            self.assertNotIn("/rounds/46/", standing_urls[0])

    @staticmethod
    def rs_game(game_code, played, round_number=1, utc_date="2026-10-01T18:00:00Z"):
        return {
            "gameCode": game_code,
            "played": played,
            "round": round_number,
            "utcDate": utc_date,
            "phaseType": {"code": "RS", "isGroupPhase": True},
        }

    def test_newly_played_game_refreshes_its_round_standings_and_season_stats(self):
        games = [self.rs_game(1, True), self.rs_game(2, False)]

        with tempfile.TemporaryDirectory() as temporary_directory:
            scrapper = self.make_scrapper(
                Path(temporary_directory),
                {"game_lists", "standings", "season_stats"},
            )
            scrapper.now_utc = datetime(2026, 12, 1, tzinfo=timezone.utc)
            fake_client = FakeClient(games)
            scrapper.client = fake_client
            scrapper.extract_season("E2026")

            fake_client.calls.clear()
            fake_client.games = [self.rs_game(1, True), self.rs_game(2, True)]
            scrapper.extract_season("E2026")

            standing_urls = [call[0] for call in fake_client.calls if "/rounds/" in call[0]]
            self.assertEqual(len(standing_urls), len(EuroScrapas.STANDING_TYPES))
            self.assertTrue(all("/rounds/1/" in url for url in standing_urls))
            stat_calls = [call for call in fake_client.calls if "/statistics/" in call[0]]
            self.assertTrue(stat_calls)
            self.assertIn("E2026/v2/games", scrapper.changed_resources)

    def test_old_unchanged_rounds_are_not_refetched_and_report_no_changes(self):
        games = [self.rs_game(1, True)]

        with tempfile.TemporaryDirectory() as temporary_directory:
            scrapper = self.make_scrapper(
                Path(temporary_directory),
                {"game_lists", "standings", "season_stats"},
            )
            scrapper.now_utc = datetime(2026, 12, 1, tzinfo=timezone.utc)
            fake_client = FakeClient(games)
            scrapper.client = fake_client
            scrapper.extract_season("E2026")

            fake_client.calls.clear()
            scrapper.changed_resources.clear()
            scrapper.extract_season("E2026")

            self.assertEqual([call[0] for call in fake_client.calls],
                             ["https://api-live.euroleague.net/v2/competitions/E/seasons/E2026/games"])
            self.assertEqual(scrapper.changed_resources, [])

    def test_recent_round_keeps_refreshing_within_the_hot_window(self):
        games = [self.rs_game(1, True, utc_date="2026-11-30T18:00:00Z")]

        with tempfile.TemporaryDirectory() as temporary_directory:
            scrapper = self.make_scrapper(
                Path(temporary_directory),
                {"game_lists", "standings"},
            )
            scrapper.now_utc = datetime(2026, 12, 1, tzinfo=timezone.utc)
            fake_client = FakeClient(games)
            scrapper.client = fake_client
            scrapper.extract_season("E2026")

            fake_client.calls.clear()
            scrapper.extract_season("E2026")
            self.assertTrue(any(call[0].endswith("/basicstandings") for call in fake_client.calls))

            fake_client.calls.clear()
            scrapper.now_utc = datetime(2026, 12, 3, tzinfo=timezone.utc)
            scrapper.extract_season("E2026")
            self.assertFalse(any(call[0].endswith("/basicstandings") for call in fake_client.calls))

    def test_season_level_data_is_rechecked_daily_even_without_games(self):
        games = [self.rs_game(1, False)]

        with tempfile.TemporaryDirectory() as temporary_directory:
            scrapper = self.make_scrapper(
                Path(temporary_directory),
                {"game_lists", "clubs", "rounds"},
            )
            scrapper.now_utc = datetime(2026, 9, 24, 2, tzinfo=timezone.utc)
            fake_client = FakeClient(games)
            scrapper.client = fake_client
            scrapper.extract_season("E2026")

            fake_client.calls.clear()
            scrapper.now_utc = datetime(2026, 9, 24, 12, tzinfo=timezone.utc)
            scrapper.extract_season("E2026")
            self.assertFalse(any(call[0].endswith("/clubs") for call in fake_client.calls))

            scrapper.now_utc = datetime(2026, 9, 25, 2, tzinfo=timezone.utc)
            scrapper.extract_season("E2026")
            self.assertTrue(any(call[0].endswith("/clubs") for call in fake_client.calls))
            self.assertTrue(any(call[0].endswith("/rounds") for call in fake_client.calls))

    def test_completed_seasons_are_never_hot(self):
        games = [self.rs_game(1, True, utc_date="2026-05-20T18:00:00Z")]

        with tempfile.TemporaryDirectory() as temporary_directory:
            scrapper = self.make_scrapper(
                Path(temporary_directory),
                {"game_lists", "standings"},
                season_code="E2025",
                year=2026,
            )
            scrapper.now_utc = datetime(2026, 5, 21, tzinfo=timezone.utc)
            fake_client = FakeClient(games)
            scrapper.client = fake_client
            scrapper.extract_season("E2025")

            fake_client.calls.clear()
            scrapper.extract_season("E2025")
            self.assertEqual(fake_client.calls, [])


if __name__ == "__main__":
    unittest.main()
