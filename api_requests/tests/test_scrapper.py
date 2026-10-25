from argparse import Namespace
from datetime import datetime, timezone
import io
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
    ):
        scrapper = EuroScrapas(
            competition="euroleague",
            season_codes=[season_code],
            datasets=datasets,
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
                {"game_lists", "game_stats", "shooting_charts"},
            )
            fake_client = FakeClient(games)
            scrapper.client = fake_client

            scrapper.extract_season("E2026")

            store = BronzeStore(root / "bronze", "euroleague", "E2026")
            self.assertEqual(store.read_json("v2/games")["data"], games)
            self.assertTrue(self.stored(root, "E2026", "v2/game_stats/1"))
            self.assertFalse(self.stored(root, "E2026", "v2/game_stats/2"))
            self.assertTrue(self.stored(root, "E2026", "live/1/shooting_charts"))
            self.assertFalse(self.stored(root, "E2026", "live/2/shooting_charts"))

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
                {"game_lists", "game_stats", "shooting_charts"},
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
            shot_calls = [
                call for call in fake_client.calls if call[0].endswith("/Points")
            ]
            self.assertEqual(len(game_list_calls), 2)
            self.assertEqual(len(game_stat_calls), 1)
            self.assertEqual(len(shot_calls), 1)

    def test_live_detail_is_not_requested_before_2007(self):
        games = [
            {"gameCode": 1, "played": True, "round": 1, "phaseType": {"code": "RS"}},
        ]

        with tempfile.TemporaryDirectory() as temporary_directory:
            scrapper = self.make_scrapper(
                Path(temporary_directory),
                {"game_lists", "shooting_charts"},
                season_code="E2006",
                year=2006,
            )
            fake_client = FakeClient(games)
            scrapper.client = fake_client

            scrapper.extract_season("E2006")

            self.assertFalse(
                any(call[0].endswith("/Points") for call in fake_client.calls)
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

    def test_default_datasets_include_only_the_used_live_endpoints(self):
        parser = ConfigParser(year_today=2026)
        parser.parse_arguments(Namespace(
            competition="euroleague", season_code=["2025"], dataset=["all"],
            failed_extractions_limit=500, game_code_start=1,
            refresh_current=False, request_interval=0,
        ))
        self.assertIn("play_by_play", parser.datasets)
        self.assertIn("shooting_charts", parser.datasets)
        self.assertEqual(parser.LIVE_ENDPOINTS, EuroScrapas.LIVE_DATASETS)
        self.assertNotIn("live_boxscores", parser.valid_datasets)

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

    def test_team_stats_are_fetched_per_phase_and_mode_without_a_sort_statistic(self):
        games = [self.rs_game(1, True)]

        with tempfile.TemporaryDirectory() as temporary_directory:
            scrapper = self.make_scrapper(
                Path(temporary_directory),
                {"game_lists", "season_stats"},
            )
            scrapper.now_utc = datetime(2026, 12, 1, tzinfo=timezone.utc)
            fake_client = FakeClient(games)
            scrapper.client = fake_client
            scrapper.extract_season("E2026")

            team_calls = [call for call in fake_client.calls if "/statistics/teams/" in call[0]]
            player_calls = [call for call in fake_client.calls if "/statistics/players/" in call[0]]
            # 2 feeds x accumulated only x (all, RS)
            self.assertEqual(len(team_calls), 4)
            self.assertEqual({url.rsplit("/", 1)[1] for url, _ in team_calls},
                             {"traditional", "advanced"})
            self.assertEqual({params["StatisticMode"] for _, params in team_calls},
                             {"accumulated"})
            # 4 feeds x 2 modes x (all, RS)
            self.assertEqual(len(player_calls), 16)
            self.assertTrue(all("Statistic" not in params and "StatisticSortMode" not in params
                                for _, params in team_calls))
            self.assertEqual({params.get("PhaseTypeCode") for _, params in team_calls}, {None, "RS"})
            self.assertTrue(all(params["Statistic"] for _, params in player_calls))
            self.assertTrue(scrapper.store.exists(
                "v3/season_stats/teams_advanced_RS_accumulated"))

    def stats_scrapper(self, root, answers):
        """A scrapper whose client returns the next queued answer per resource URL."""
        scrapper = self.make_scrapper(root, {"season_stats"})
        scrapper.activate_scope("E2026")

        class QueueClient:
            def get_json(self, url, params=None):
                return reply(answers.pop(0), url)

        scrapper.client = QueueClient()
        scrapper.stale_retries = 0
        return scrapper

    @staticmethod
    def teams(*clubs, games=1):
        return {"teams": [{"team": {"code": club}, "gamesPlayed": games} for club in clubs]}

    def fetch_stats(self, scrapper, resource):
        return scrapper.fetch_to_cache(source="v3.test", url="https://example.test/stats",
                                       resource=resource, force=True, keep_if_worse=True)

    def test_a_stats_answer_with_fewer_clubs_keeps_the_stored_version(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            answers = [self.teams("MAD", "BAR", "OLY"), self.teams("MAD", "BAR")]
            scrapper = self.stats_scrapper(Path(temporary_directory), answers)
            resource = "v3/season_stats/teams_traditional_RS_accumulated"
            self.fetch_stats(scrapper, resource)
            with patch("sys.stdout", io.StringIO()) as out:
                returned = self.fetch_stats(scrapper, resource)
            self.assertEqual(len(returned["teams"]), 3)
            self.assertEqual(len(scrapper.store.read_json(resource)["teams"]), 3)
            self.assertEqual(scrapper.kept_resources, [f"E2026/{resource}"])
            self.assertIn("[kept]", out.getvalue())
            self.assertIn("API answered 2 clubs / 2 games, stored version has 3 / 3",
                          out.getvalue())
            manifest = [json.loads(line) for line in
                        (scrapper.store.directory / "manifest.jsonl").read_text().splitlines()]
            self.assertEqual(manifest[-1]["stored_as"], None)
            self.assertIn("API answered 2 clubs", manifest[-1]["rejected"])

    def test_fewer_total_games_in_a_totals_feed_keep_the_stored_version(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            answers = [self.teams("MAD", "BAR", games=2), self.teams("MAD", "BAR", games=1)]
            scrapper = self.stats_scrapper(Path(temporary_directory), answers)
            resource = "v3/season_stats/teams_traditional_all_accumulated"
            self.fetch_stats(scrapper, resource)
            with patch("sys.stdout", io.StringIO()):
                self.fetch_stats(scrapper, resource)
            self.assertEqual(scrapper.store.read_json(resource)["teams"][0]["gamesPlayed"], 2)
            self.assertEqual(len(scrapper.kept_resources), 1)

    def test_a_bigger_or_equal_stats_answer_is_stored(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            answers = [self.teams("MAD", games=1), self.teams("MAD", "BAR", games=2),
                       {"players": [{"player": {"team": {"code": "MAD"}}, "gamesPlayed": 2},
                                    {"player": {"team": {"code": "BAR"}}, "gamesPlayed": 2},
                                    {"player": {"team": None}, "gamesPlayed": 1}]}]
            scrapper = self.stats_scrapper(Path(temporary_directory), answers)
            resource = "v3/season_stats/teams_traditional_all_accumulated"
            self.fetch_stats(scrapper, resource)
            self.fetch_stats(scrapper, resource)
            self.assertEqual(len(scrapper.store.read_json(resource)["teams"]), 2)
            player_resource = "v3/season_stats/players_traditional_RS_perGame"
            self.fetch_stats(scrapper, player_resource)
            self.assertEqual(scrapper.kept_resources, [])

    def test_a_per_game_feed_may_shrink_but_not_empty(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            answers = [self.teams("MAD", "BAR", "OLY"), self.teams("MAD", "BAR"), {"teams": []}]
            scrapper = self.stats_scrapper(Path(temporary_directory), answers)
            resource = "v3/season_stats/teams_traditional_all_perGame"
            self.fetch_stats(scrapper, resource)
            self.fetch_stats(scrapper, resource)  # fewer qualifying clubs: stored
            self.assertEqual(len(scrapper.store.read_json(resource)["teams"]), 2)
            with patch("sys.stdout", io.StringIO()) as out:
                self.fetch_stats(scrapper, resource)  # empty: kept
            self.assertEqual(len(scrapper.store.read_json(resource)["teams"]), 2)
            self.assertEqual(scrapper.kept_resources, [f"E2026/{resource}"])
            self.assertIn("API answered 0 clubs, stored version has 2", out.getvalue())

    @staticmethod
    def standings(*games):
        return {"teams": [{"club": {"code": code}, "gamesPlayed": played}
                          for code, played in games]}

    def test_a_standings_answer_a_game_behind_keeps_the_stored_version(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            answers = [self.standings(("MAD", 2), ("BAR", 2)),
                       self.standings(("MAD", 1), ("BAR", 2)),
                       self.standings(("MAD", 2), ("BAR", 2)),
                       self.standings(("MAD", 3), ("BAR", 3))]
            scrapper = self.stats_scrapper(Path(temporary_directory), answers)
            resource = "v3/standings/RS_2_basicstandings"
            self.fetch_stats(scrapper, resource)
            with patch("sys.stdout", io.StringIO()) as out:
                self.fetch_stats(scrapper, resource)
            self.assertEqual(scrapper.store.read_json(resource)["teams"][0]["gamesPlayed"], 2)
            self.assertEqual(scrapper.kept_resources, [f"E2026/{resource}"])
            self.assertIn("API answered 2 clubs / 3 games, stored version has 2 / 4",
                          out.getvalue())
            self.fetch_stats(scrapper, resource)  # equal: stored as usual
            self.fetch_stats(scrapper, resource)  # newer: replaces
            self.assertEqual(scrapper.store.read_json(resource)["teams"][0]["gamesPlayed"], 3)
            self.assertEqual(len(scrapper.kept_resources), 1)

    def test_a_worse_answer_is_asked_again_until_a_complete_one_arrives(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            answers = [self.teams("MAD", "BAR", "OLY"), {"teams": []}, {"teams": []},
                       self.teams("MAD", "BAR", "OLY", "ZAL")]
            scrapper = self.stats_scrapper(Path(temporary_directory), answers)
            scrapper.stale_retries = 5
            resource = "v3/season_stats/teams_traditional_all_accumulated"
            self.fetch_stats(scrapper, resource)
            with patch("sys.stdout", io.StringIO()) as out:
                self.fetch_stats(scrapper, resource)
            self.assertEqual(answers, [])
            self.assertEqual(len(scrapper.store.read_json(resource)["teams"]), 4)
            self.assertEqual(scrapper.kept_resources, [])
            self.assertEqual(out.getvalue().count("[stale]"), 2)
            self.assertIn("(retry 2/5)", out.getvalue())

    def test_a_feed_that_stays_worse_is_kept_after_every_retry(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            answers = [self.teams("MAD", "BAR"), *[{"teams": []}] * 3]
            scrapper = self.stats_scrapper(Path(temporary_directory), answers)
            scrapper.stale_retries = 2
            resource = "v3/season_stats/teams_traditional_all_accumulated"
            self.fetch_stats(scrapper, resource)
            with patch("sys.stdout", io.StringIO()) as out:
                self.fetch_stats(scrapper, resource)
            self.assertEqual(answers, [])
            self.assertEqual(len(scrapper.store.read_json(resource)["teams"]), 2)
            self.assertEqual(scrapper.kept_resources, [f"E2026/{resource}"])
            self.assertIn("in all 3 attempt(s)", out.getvalue())

    def fetch_checked(self, scrapper, resource, expected_games, fallback_params=()):
        return scrapper.fetch_to_cache(
            source="v3.test", url="https://example.test/stats", resource=resource,
            force=True, keep_if_worse=True, expected_games=expected_games,
            fallback_params=fallback_params)

    def test_an_answer_missing_a_club_that_played_is_asked_again(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            # An older snapshot (2 clubs) is not smaller than the stored one (2 clubs).
            answers = [self.teams("MAD", "BAR"), self.teams("MAD", "BAR"),
                       self.teams("MAD", "BAR", "OLY")]
            scrapper = self.stats_scrapper(Path(temporary_directory), answers)
            scrapper.stale_retries = 3
            resource = "v3/season_stats/teams_traditional_RS_perGame"
            self.fetch_stats(scrapper, resource)
            with patch("sys.stdout", io.StringIO()) as out:
                self.fetch_checked(scrapper, resource, {"MAD": 1, "BAR": 1, "OLY": 1})
            self.assertEqual(answers, [])
            self.assertEqual(len(scrapper.store.read_json(resource)["teams"]), 3)
            self.assertIn("API covers 2 of 3 club-games played", out.getvalue())
            self.assertEqual(scrapper.behind_resources, [])

    def test_a_first_answer_that_stays_incomplete_is_stored_and_listed_as_behind(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            answers = [self.teams("MAD")] * 3
            scrapper = self.stats_scrapper(Path(temporary_directory), answers)
            scrapper.stale_retries = 2
            resource = "v3/season_stats/teams_traditional_RS_perGame"
            with patch("sys.stdout", io.StringIO()) as out:
                self.fetch_checked(scrapper, resource, {"MAD": 1, "BAR": 1, "OLY": 1})
            self.assertEqual(answers, [])
            self.assertEqual(len(scrapper.store.read_json(resource)["teams"]), 1)
            self.assertEqual(scrapper.kept_resources, [])
            self.assertEqual(scrapper.behind_resources, [f"E2026/{resource}"])
            self.assertIn("no stored version to keep", out.getvalue())
            self.assertIn("[behind]", out.getvalue())

    def test_a_stale_answer_that_is_not_worse_is_retried_and_listed_as_behind(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            answers = [self.teams("MAD", "BAR", games=2)] * 4
            scrapper = self.stats_scrapper(Path(temporary_directory), answers)
            scrapper.stale_retries = 2
            resource = "v3/season_stats/teams_traditional_RS_accumulated"
            self.fetch_stats(scrapper, resource)
            with patch("sys.stdout", io.StringIO()) as out:
                self.fetch_checked(scrapper, resource, {"MAD": 3, "BAR": 3})
            self.assertEqual(answers, [])
            self.assertEqual(out.getvalue().count("[stale]"), 3)
            self.assertIn("[behind]", out.getvalue())
            self.assertIn("covers 4 of 6 club-games", out.getvalue())
            self.assertEqual(scrapper.behind_resources, [f"E2026/{resource}"])
            self.assertEqual(scrapper.kept_resources, [])

    def test_a_stale_answer_to_a_complete_stored_version_is_asked_once_and_not_listed(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            answers = [self.teams("MAD", "BAR", games=3), self.teams("MAD", "BAR", games=2)]
            scrapper = self.stats_scrapper(Path(temporary_directory), answers)
            scrapper.stale_retries = 4
            resource = "v3/season_stats/teams_traditional_RS_perGame"
            self.fetch_checked(scrapper, resource, {"MAD": 3, "BAR": 3})
            with patch("sys.stdout", io.StringIO()) as out:
                self.fetch_checked(scrapper, resource, {"MAD": 3, "BAR": 3},
                                   [self.RANGE_KEY])
            self.assertEqual(answers, [])
            self.assertEqual(out.getvalue().count("[request]"), 1)
            self.assertEqual(scrapper.store.read_json(resource)["teams"][0]["gamesPlayed"], 3)
            self.assertIn("[current]", out.getvalue())
            self.assertIn("API covers 4 of 6 club-games played", out.getvalue())
            self.assertNotIn("[kept]", out.getvalue())
            self.assertEqual(scrapper.kept_resources, [])
            self.assertEqual(scrapper.behind_resources, [])
            manifest = [json.loads(line) for line in
                        (scrapper.store.directory / "manifest.jsonl").read_text().splitlines()]
            self.assertIn("API covers 4 of 6", manifest[-1]["rejected"])

    def test_a_complete_answer_to_a_complete_stored_version_is_still_stored(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            corrected = {"teams": [{"team": {"code": "MAD"}, "gamesPlayed": 3, "points": 1},
                                   {"team": {"code": "BAR"}, "gamesPlayed": 3}]}
            answers = [self.teams("MAD", "BAR", games=3), corrected]
            scrapper = self.stats_scrapper(Path(temporary_directory), answers)
            resource = "v3/season_stats/teams_traditional_RS_accumulated"
            self.fetch_checked(scrapper, resource, {"MAD": 3, "BAR": 3})
            self.fetch_checked(scrapper, resource, {"MAD": 3, "BAR": 3})
            self.assertEqual(scrapper.store.read_json(resource), corrected)

    def test_a_worse_answer_to_a_stored_version_that_is_behind_is_kept_and_listed(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            answers = [self.teams("MAD", "BAR", games=2), self.teams("MAD", "BAR", games=1)]
            scrapper = self.stats_scrapper(Path(temporary_directory), answers)
            scrapper.stale_retries = 0
            resource = "v3/season_stats/teams_traditional_RS_accumulated"
            self.fetch_stats(scrapper, resource)
            with patch("sys.stdout", io.StringIO()) as out:
                self.fetch_checked(scrapper, resource, {"MAD": 3, "BAR": 3})
            self.assertEqual(scrapper.store.read_json(resource)["teams"][0]["gamesPlayed"], 2)
            self.assertEqual(scrapper.kept_resources, [f"E2026/{resource}"])
            self.assertEqual(scrapper.behind_resources, [f"E2026/{resource}"])
            self.assertIn("[kept]", out.getvalue())

    def test_a_per_game_snapshot_covering_less_than_a_behind_stored_one_is_kept(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            answers = [self.teams("MAD", "BAR", games=2), self.teams("MAD", "BAR", games=1)]
            scrapper = self.stats_scrapper(Path(temporary_directory), answers)
            scrapper.stale_retries = 0
            resource = "v3/season_stats/teams_traditional_RS_perGame"
            self.fetch_stats(scrapper, resource)
            with patch("sys.stdout", io.StringIO()) as out:
                self.fetch_checked(scrapper, resource, {"MAD": 3, "BAR": 3})
            self.assertEqual(scrapper.store.read_json(resource)["teams"][0]["gamesPlayed"], 2)
            self.assertEqual(scrapper.kept_resources, [f"E2026/{resource}"])
            self.assertIn("API covers 2 of 6 club-games, stored version covers 4", out.getvalue())

    def test_coverage_counts_whole_club_games(self):
        coverage = EuroScrapas.stats_coverage(self.teams("MAD", "BAR", games=3.0), {"MAD": 3, "BAR": 3})
        self.assertEqual(coverage, 6)
        self.assertIsInstance(coverage, int)

    def test_an_incomplete_answer_covering_more_than_the_stored_one_is_stored(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            answers = [self.teams("MAD", "BAR", games=1), self.teams("MAD", "BAR", games=2)]
            scrapper = self.stats_scrapper(Path(temporary_directory), answers)
            resource = "v3/season_stats/teams_traditional_RS_accumulated"
            self.fetch_stats(scrapper, resource)
            with patch("sys.stdout", io.StringIO()):
                self.fetch_checked(scrapper, resource, {"MAD": 3, "BAR": 3})
            self.assertEqual(scrapper.store.read_json(resource)["teams"][0]["gamesPlayed"], 2)
            self.assertEqual(scrapper.kept_resources, [])
            self.assertEqual(scrapper.behind_resources, [f"E2026/{resource}"])

    def test_a_complete_answer_is_stored_and_not_listed_as_behind(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            answers = [self.teams("MAD", "BAR", games=3)]
            scrapper = self.stats_scrapper(Path(temporary_directory), answers)
            resource = "v3/season_stats/teams_traditional_RS_accumulated"
            self.fetch_checked(scrapper, resource, {"MAD": 3, "BAR": 3})
            self.assertEqual(len(scrapper.store.read_json(resource)["teams"]), 2)
            self.assertEqual(scrapper.behind_resources, [])

    def test_a_player_feed_is_complete_when_each_club_has_a_player_with_every_game(self):
        def player(club, games):
            return {"player": {"team": {"code": club}}, "gamesPlayed": games}

        expected = {"MAD": 3, "BAR": 3}
        coverage = EuroScrapas.stats_coverage
        self.assertEqual(coverage({"players": [
            player("MAD", 3), player("MAD", 1), player("BAR", 3), player("BAR", 2)]}, expected), 6)
        self.assertEqual(coverage({"players": [
            player("MAD", 2), player("MAD", 1), player("BAR", 3)]}, expected), 5)

    def test_a_multi_club_code_is_neither_a_club_nor_a_missing_game(self):
        def player(club, games):
            return {"player": {"team": {"code": club}}, "gamesPlayed": games}

        payload = {"players": [player("MAD", 3), player("BAR", 3), player("BAS;TEL", 1)]}
        self.assertEqual(EuroScrapas.stats_feed_size(payload, True), (2, 7))
        self.assertEqual(EuroScrapas.stats_coverage(payload, {"MAD": 3, "BAR": 3}), 6)
        self.assertEqual(EuroScrapas.stats_coverage(payload, {"MAD": 3, "BAR": 3, "BAS;TEL": 1}), 6)

    def test_a_fresh_answer_with_a_multi_club_code_is_not_worse_than_a_stale_one(self):
        def player(club, games):
            return {"player": {"team": {"code": club}}, "gamesPlayed": games}

        stale = {"players": [player("MAD", 1), player("BAR", 1), player("BAS;TEL", 1)]}
        fresh = {"players": [player("MAD", 2), player("BAR", 2)]}
        resource = "v3/season_stats/players_scoring_all_accumulated"
        self.assertIsNone(EuroScrapas.worse_stats_answer(stale, fresh, resource))

    def fallback_client(self, answers):
        sent = []

        class FallbackClient:
            def get_json(self, url, params=None):
                sent.append({key: value for key, value in params.items() if key != "_"})
                return reply(answers.pop(0), url)

        return FallbackClient(), sent

    RANGE_KEY = {"SeasonMode": "Range", "FromSeasonCode": "E2026", "ToSeasonCode": "E2026"}

    def test_a_complete_fallback_key_replaces_a_stale_main_key_and_is_recorded(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            scrapper = self.stats_scrapper(Path(temporary_directory), [])
            scrapper.stale_retries = 1
            client, sent = self.fallback_client([
                self.teams("MAD", "BAR", games=1), self.teams("MAD", "BAR", games=1),
                self.teams("MAD", "BAR", games=1), self.teams("MAD", "BAR", games=3)])
            scrapper.client = client
            resource = "v3/season_stats/teams_traditional_RS_accumulated"
            main = {"SeasonMode": "Single", "SeasonCode": "E2026"}
            with patch("sys.stdout", io.StringIO()) as out:
                scrapper.fetch_to_cache(
                    source="v3.test", url="https://example.test/stats", params=main,
                    resource=resource, force=True, keep_if_worse=True,
                    expected_games={"MAD": 3, "BAR": 3},
                    fallback_params=[{"SeasonMode": "Range"}, self.RANGE_KEY])
            self.assertEqual(len(sent), 4)  # main key twice, then one request per fallback key
            self.assertEqual(scrapper.store.read_json(resource)["teams"][0]["gamesPlayed"], 3)
            self.assertEqual(scrapper.behind_resources, [])
            self.assertIn("(fallback key 2/2)", out.getvalue())
            manifest = [json.loads(line) for line in
                        (scrapper.store.directory / "manifest.jsonl").read_text().splitlines()]
            self.assertEqual(manifest[-1]["params"], self.RANGE_KEY)
            self.assertTrue(manifest[-1]["stored_as"])

    def test_incomplete_fallback_keys_leave_the_feed_behind(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            scrapper = self.stats_scrapper(Path(temporary_directory), [])
            scrapper.stale_retries = 0
            client, sent = self.fallback_client([self.teams("MAD", "BAR", games=1)] * 3)
            scrapper.client = client
            resource = "v3/season_stats/teams_traditional_RS_accumulated"
            with patch("sys.stdout", io.StringIO()):
                self.fetch_checked(scrapper, resource, {"MAD": 3, "BAR": 3},
                                   [self.RANGE_KEY, {"SeasonMode": "Range"}])
            self.assertEqual(len(sent), 3)
            self.assertEqual(scrapper.behind_resources, [f"E2026/{resource}"])

    def test_no_fallback_key_is_asked_while_the_stored_version_is_complete(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            scrapper = self.stats_scrapper(Path(temporary_directory), [])
            scrapper.stale_retries = 0
            client, sent = self.fallback_client([
                self.teams("MAD", "BAR", games=3), self.teams("MAD", "BAR", games=2)])
            scrapper.client = client
            resource = "v3/season_stats/teams_traditional_RS_accumulated"
            self.fetch_checked(scrapper, resource, {"MAD": 3, "BAR": 3}, [self.RANGE_KEY])
            with patch("sys.stdout", io.StringIO()):
                self.fetch_checked(scrapper, resource, {"MAD": 3, "BAR": 3}, [self.RANGE_KEY])
            self.assertEqual(len(sent), 2)
            self.assertEqual(scrapper.store.read_json(resource)["teams"][0]["gamesPlayed"], 3)

    def test_fallback_keys_keep_the_sort_parameters_and_follow_the_phase_rule(self):
        params = EuroScrapas.v3_stats_params("E2026", "timePlayed", "perGame", "all")
        keys = EuroScrapas.fallback_stats_params(params, "E2026", "RS")
        self.assertEqual(len(keys), 3)
        for key in keys[:2]:
            self.assertEqual(key["SeasonMode"], "Range")
            self.assertNotIn("SeasonCode", key)
            self.assertEqual((key["FromSeasonCode"], key["ToSeasonCode"]), ("E2026", "E2026"))
        self.assertNotIn("PhaseTypeCode", keys[0])
        self.assertEqual(keys[1]["PhaseTypeCode"], "RS")
        self.assertEqual(keys[2], {**params, "PhaseTypeCode": "RS"})
        for key in keys:
            for sort_param in ("Statistic", "SortDirection", "StatisticSortMode"):
                self.assertEqual(key[sort_param], params[sort_param])
        self.assertEqual(len(EuroScrapas.fallback_stats_params(params, "E2026", None)), 1)
        phase = EuroScrapas.v3_stats_params("E2026", None, "perGame", "RS")
        self.assertEqual(len(EuroScrapas.fallback_stats_params(phase, "E2026", "RS")), 1)

    def test_a_season_run_stores_fallback_answers_and_lists_the_feeds_still_behind(self):
        game = dict(self.rs_game(1, True, utc_date="2026-11-30T18:00:00Z"),
                    local={"club": {"code": "MAD"}}, road={"club": {"code": "BAR"}})

        class RangeClient(FakeClient):
            def get_json(self, url, params=None):
                if "/statistics/" not in url:
                    return super().get_json(url, params)
                self.calls.append((url, params))
                complete = params.get("SeasonMode") == "Range" and params.get("PhaseTypeCode") == "RS"
                if "/teams/advanced" in url:
                    complete = False
                return reply(EuroScrapasTests.teams("MAD", "BAR", games=1 if complete else 0), url)

        with tempfile.TemporaryDirectory() as temporary_directory:
            scrapper = self.make_scrapper(Path(temporary_directory), {"game_lists", "season_stats"})
            scrapper.now_utc = datetime(2026, 12, 1, tzinfo=timezone.utc)
            scrapper.stale_retries = 0
            scrapper.client = RangeClient([game])
            with patch("sys.stdout", io.StringIO()):
                scrapper.extract_season("E2026")
            for phase in ("all", "RS"):
                self.assertEqual(scrapper.store.read_json(
                    f"v3/season_stats/teams_traditional_{phase}_accumulated"
                )["teams"][0]["gamesPlayed"], 1)
            behind = {resource.rsplit("/", 1)[1] for resource in scrapper.behind_resources}
            self.assertEqual(behind, {f"teams_advanced_{phase}_accumulated"
                                      for phase in ("all", "RS")})

    def test_stats_requests_carry_a_cache_buster_that_is_not_recorded(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            scrapper = self.stats_scrapper(Path(temporary_directory), [self.teams("MAD")])
            sent = []

            class RecordingClient:
                def get_json(self, url, params=None):
                    sent.append(params)
                    return reply(EuroScrapasTests.teams("MAD"), url)

            scrapper.client = RecordingClient()
            scrapper.fetch_to_cache(source="v3.test", url="https://example.test/stats",
                                    params={"SeasonCode": "E2026"},
                                    resource="v3/season_stats/teams_advanced_all_accumulated",
                                    force=True, keep_if_worse=True)
            scrapper.fetch_to_cache(source="v2.test", url="https://example.test/clubs",
                                    params={"SeasonCode": "E2026"},
                                    resource="v2/clubs", force=True)
            self.assertIn("_", sent[0])
            self.assertEqual(sent[1], {"SeasonCode": "E2026"})
            manifest = [json.loads(line) for line in
                        (scrapper.store.directory / "manifest.jsonl").read_text().splitlines()]
            self.assertEqual(manifest[0]["params"], {"SeasonCode": "E2026"})

    def test_an_empty_first_stats_answer_is_stored(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            scrapper = self.stats_scrapper(Path(temporary_directory), [{"teams": []}])
            resource = "v3/season_stats/teams_advanced_RS_perGame"
            self.fetch_stats(scrapper, resource)
            self.assertEqual(scrapper.store.read_json(resource), {"teams": []})
            self.assertEqual(scrapper.kept_resources, [])

    def test_other_resources_are_stored_even_when_smaller(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            answers = [self.teams("MAD", "BAR"), self.teams("MAD")]
            scrapper = self.stats_scrapper(Path(temporary_directory), answers)
            for _ in range(2):
                scrapper.fetch_to_cache(source="v2.test", url="https://example.test/clubs",
                                        resource="v2/clubs", force=True)
            self.assertEqual(len(scrapper.store.read_json("v2/clubs")["teams"]), 1)
            self.assertEqual(scrapper.kept_resources, [])

    def test_in_one_run_a_worse_feed_is_kept_while_a_good_feed_updates(self):
        games = [self.rs_game(1, True, utc_date="2026-11-30T18:00:00Z")]

        class StatsClient(FakeClient):
            def __init__(self, games, clubs):
                super().__init__(games)
                self.clubs = clubs

            def get_json(self, url, params=None):
                if "/statistics/teams/traditional" in url:
                    self.calls.append((url, params))
                    return reply(EuroScrapasTests.teams(*self.clubs), url)
                if "/statistics/" in url:
                    self.calls.append((url, params))
                    return reply(EuroScrapasTests.teams("MAD", "BAR", "OLY"), url)
                return super().get_json(url, params)

        with tempfile.TemporaryDirectory() as temporary_directory:
            scrapper = self.make_scrapper(Path(temporary_directory), {"game_lists", "season_stats"})
            scrapper.now_utc = datetime(2026, 12, 1, tzinfo=timezone.utc)
            scrapper.client = StatsClient(games, ["MAD", "BAR", "OLY"])
            with patch("sys.stdout", io.StringIO()):
                scrapper.extract_season("E2026")
            # Second run within the hot window: traditional answers stale, the rest fine.
            scrapper.client = StatsClient(games, ["MAD"])
            with patch("sys.stdout", io.StringIO()):
                scrapper.extract_season("E2026")
            kept = {resource.rsplit("/", 1)[1] for resource in scrapper.kept_resources}
            self.assertEqual(kept, {f"teams_traditional_{phase}_accumulated"
                                    for phase in ("all", "RS")})
            self.assertEqual(len(scrapper.store.read_json(
                "v3/season_stats/teams_traditional_RS_accumulated")["teams"]), 3)
            self.assertFalse(scrapper.store.exists("v3/season_stats/teams_traditional_RS_perGame"))

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
