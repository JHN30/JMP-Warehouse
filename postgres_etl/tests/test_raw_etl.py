import json
import shutil
import sys
import tempfile
import types
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import available_seasons, build_parser, requested_seasons
from flat_loader import FlatDatabaseLoader
from flat_schema import TABLES, create_table_sql
from flat_transform import FlatSeason
from raw_transform import CORRECTED_REASON, RawSeason
from shared import BronzeStore


class RawEtlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = BronzeStore(self.root / "bronze", "euroleague", "E2025")
        self.write("v2/seasons.json", {
            "data": [{"code": "E2025", "name": "EuroLeague 2025-26", "year": 2025,
                      "winner": {"code": "OLY"}}]
        }, store=BronzeStore(self.root / "bronze", "euroleague", "_catalog"))
        self.write("v2/games.json", {"data": [
            {"gameCode": 1, "played": True, "utcDate": "2025-10-01T18:00:00Z",
             "phaseType": {"code": "RS"}, "round": 1,
             "local": {"club": {"code": "MAD"}, "score": 80,
                       "partials": {"partials1": 20, "extraPeriods": {"1": 8}}},
             "road": {"club": {"code": "BAR"}, "score": 70,
                      "partials": {"partials1": 15, "extraPeriods": {"1": 9}}},
             "winner": {"code": "OLY"}, "referee1": {"code": "R1", "name": "Ref"}},
            {"gameCode": 2, "played": False, "utcDate": "2026-04-01T18:00:00Z",
             "local": {"club": {"code": "MAD"}, "score": 0,
                       "partials": {"partials1": 0, "extraPeriods": {}}},
             "road": {"club": {"code": "OLY"}, "score": 0,
                      "partials": {"partials1": 0, "extraPeriods": {}}},
             "winner": {"code": "OLY"}}
        ]})
        person = {"code": "000123", "name": "Test Player"}
        registration = {"person": person, "club": {"code": "MAD"}, "type": "J",
                        "startDate": "2025-07-01", "externalId": 123, "active": True}
        self.write("v2/season_people_pages/offset_000000.json",
                   {"data": [registration], "total": 1})
        self.write("live/1/shooting_charts.json", {"Rows": [
            {"NUM_ANOT": 1, "TEAM": "MAD   ", "ID_PLAYER": "P000123  ",
             "POINTS": 2, "COORD_X": 3, "COORD_Y": 4},
            {"NUM_ANOT": 2, "TEAM": "MAD   ", "ID_PLAYER": "P000123  ",
             "POINTS": 0, "COORD_X": 4, "COORD_Y": 5}]})

    def write(self, relative, value, store=None):
        (store or self.store).write(relative.removesuffix(".json"),
                                    json.dumps(value).encode("utf-8"))

    def season(self):
        return RawSeason(self.root, "euroleague", "E2025")

    def test_scope_and_ranges_use_only_cached_competition(self):
        self.assertEqual(available_seasons(self.root, "euroleague"), ["E2025"])
        self.assertEqual(available_seasons(self.root, "eurocup"), [])
        parser = build_parser()
        self.assertEqual(requested_seasons(["all"], "euroleague", ["E2025"], parser), ["E2025"])
        self.assertEqual(requested_seasons(["2024-2025"], "euroleague", ["E2025"], parser),
                         ["E2025"])
        self.assertEqual(requested_seasons(["E2025"], "euroleague", ["E2025"], parser),
                         ["E2025"])

    def test_bronze_versions_name_only_files_actually_read(self):
        old = self.store.latest_path("v2/games")
        self.store.write("v2/games", b'{"data":[]}',
                         fetched_at=datetime(2099, 1, 1, tzinfo=timezone.utc))
        latest = self.store.latest_path("v2/games")
        self.store.write("v2/rounds", b'{"data":[]}')
        season = self.season()
        season.begin_table()
        list(season.rows("games", season.files("games")))
        self.assertNotEqual(old, latest)
        self.assertEqual(season.bronze_versions(),
                         [latest.relative_to(self.root / "bronze").as_posix()])

    def test_catalog_and_auxiliary_reads_are_recorded_per_table(self):
        self.store.write("v2/game_stats/1", json.dumps({"local": {"players": [{
            "player": {"person": {"code": "000123"}, "club": {"code": "MAD"},
                       "dorsal": "1"}
        }]}}).encode("utf-8"))
        season = self.season()
        season.begin_table()
        list(season.rows("seasons", season.files("seasons")))
        self.assertEqual(len(season.bronze_versions()), 1)
        self.assertIn("/_catalog/", season.bronze_versions()[0])

        season.begin_table()
        list(season.rows("shots", season.files("shots")))
        shot_versions = season.bronze_versions()
        self.assertTrue(any("/live/1/shooting_charts/" in path for path in shot_versions))
        self.assertTrue(any("/v2/game_stats/1/" in path for path in shot_versions))
        self.assertFalse(any("/_catalog/" in path for path in shot_versions))

        season.begin_table()
        list(season.rows("shots", season.files("shots")))
        self.assertEqual(season.bronze_versions(), shot_versions)

    def test_champion_is_not_match_winner_and_future_game_survives(self):
        rows = list(self.season().rows("games"))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["match_winner_club_code"], "MAD")
        self.assertEqual(rows[0]["champion_club_code"], "OLY")
        self.assertFalse(rows[1]["played"])
        self.assertIsNone(rows[1]["local_score"])
        self.assertIsNone(rows[1]["road_score"])
        self.assertIsNone(rows[1]["match_winner_club_code"])

    def test_registration_overlap_is_deduplicated(self):
        self.assertEqual(len(list(self.season().rows("people"))), 1)
        self.assertEqual(len(list(self.season().rows("registrations"))), 1)

    def test_shots_include_misses_and_normalize_person_code(self):
        shots = list(self.season().rows("shots"))
        self.assertEqual([shot["points"] for shot in shots], [2, 0])
        self.assertEqual(shots[0]["player_code"], "P000123")
        self.assertEqual(shots[0]["person_code"], "000123")

    def test_periods_and_officials(self):
        periods = list(self.season().rows("game_period_scores"))
        self.assertEqual(len(periods), 4)
        self.assertEqual({row["game_code"] for row in periods}, {1})
        self.assertEqual({row["period_number"] for row in periods}, {1, 5})
        self.assertEqual(len(list(self.season().rows("game_officials"))), 1)

    def box_player(self, person_code, name, dorsal, club="MAD"):
        return {"player": {"person": {"code": person_code, "name": name},
                           "club": {"code": club}, "dorsal": dorsal},
                "stats": {"points": 2, "timePlayed": 600}}

    def test_live_rows_keep_the_original_code_next_to_the_person_code(self):
        self.write("v2/game_stats/1.json", {"local": {"players": [
            self.box_player("KLT", "HEURTEL, THOMAS", "8")]}, "road": {"players": []}})
        self.write("live/1/play_by_play.json", {"FirstQuarter": [
            {"NUMBEROFPLAY": 1, "CODETEAM": "MAD ", "PLAYER_ID": "PKLT      ", "DORSAL": "8"},
            {"NUMBEROFPLAY": 2, "CODETEAM": "MAD ", "PLAYER_ID": "CO_A"},
            {"NUMBEROFPLAY": 3, "CODETEAM": "MAD ", "PLAYER_ID": "          "},
        ]})
        rows = list(self.season().rows("play_by_play"))
        self.assertEqual([(row["player_code"], row["person_code"], row["person_code_method"])
                          for row in rows],
                         [("PKLT", "KLT", "live_id"), ("CO_A", None, None), (None, None, None)])

    def test_wrong_live_ids_are_matched_by_jersey_name_or_play_by_play(self):
        # Kanter E2008: the live API used P000936, the v2 box score has 000110.
        self.write("v2/game_stats/1.json", {"local": {"players": [
            self.box_player("000110", "KANTER, ENES", "11"),
            self.box_player("THY", "MILOSEVIC, STRAHINJA", "4")]}, "road": {"players": []}})
        self.write("live/1/play_by_play.json", {"FirstQuarter": [
            {"NUMBEROFPLAY": 1, "CODETEAM": "MAD", "PLAYER_ID": "P000936", "DORSAL": "11",
             "PLAYER": "KANTER, ENES"},
            {"NUMBEROFPLAY": 2, "CODETEAM": "MAD", "PLAYER_ID": "PTGY", "DORSAL": "",
             "PLAYER": "MILOSEVIC, STRAHINJA"},
            {"NUMBEROFPLAY": 3, "CODETEAM": "MAD", "PLAYER_ID": "PZZZ", "DORSAL": "99",
             "PLAYER": "NOBODY, KNOWN"},
        ]})
        self.write("live/1/shooting_charts.json", {"Rows": [
            {"NUM_ANOT": 1, "TEAM": "MAD", "ID_PLAYER": "P000936", "PLAYER": "KANTR, E."}]})
        pbp = [(row["person_code"], row["person_code_method"])
               for row in self.season().rows("play_by_play")]
        self.assertEqual(pbp, [("000110", "jersey_number"), ("THY", "name"), (None, "unmatched")])
        shots = [(row["person_code"], row["person_code_method"]) for row in self.season().rows("shots")]
        self.assertEqual(shots, [("000110", "play_by_play")])

    def test_unrecorded_box_score_measures_become_null_and_are_listed(self):
        def player(code, points, plus_minus):
            return {"player": {"person": {"code": code}, "club": {"code": "MAD"}},
                    "stats": {"points": points, "plusMinus": plus_minus, "timePlayed": 600,
                              "foulsReceived": 0}}
        self.write("v2/game_stats/1.json", {
            "local": {"players": [player("A", 10, 0), player("B", 0, 0)],
                      "total": {"points": 10, "plusMinus": 0}},
            "road": {"players": [player("C", 8, 0)], "total": {"points": 8, "plusMinus": 0}},
        })
        players = list(self.season().rows("game_player_stats"))
        self.assertEqual([p["payload"]["stats"]["plusMinus"] for p in players], [None, None, None])
        self.assertEqual([p["points"] for p in players], [10, 0, 8])  # a real 0 stays 0
        teams = list(self.season().rows("game_team_stats"))
        self.assertIsNone(teams[0]["payload"]["total"]["plusMinus"])
        gaps = list(self.season().rows("game_stat_gaps"))
        self.assertEqual([(g["game_code"], g["stat_name"]) for g in gaps],
                         [(1, "fouls_drawn"), (1, "plus_minus")])

    def test_points_are_corrected_only_when_the_makes_prove_them(self):
        def player(code, points, made2, made3, valuation):
            return {"player": {"person": {"code": code, "name": code}, "club": {"code": "MAD"}},
                    "stats": {"points": points, "fieldGoalsMade2": made2, "fieldGoalsMade3": made3,
                              "freeThrowsMade": 0, "valuation": valuation, "timePlayed": 600}}
        # Game 1 ends MAD 80-70 BAR. MAD's makes add up to 80 but its points to 90,
        # so A's 30 points are wrong. BAR's points match the score while a make is
        # off (68): no rule knows which value is right, so BAR is left as given.
        self.write("v2/game_stats/1.json", {
            "local": {"players": [player("A", 30, 10, 0, 25), player("B", 60, 21, 6, 40)],
                      "total": {"points": 90, "fieldGoalsMade2": 31, "fieldGoalsMade3": 6,
                                "freeThrowsMade": 0, "valuation": 65}},
            "road": {"players": [player("C", 70, 34, 0, 50)],
                     "total": {"points": 70, "fieldGoalsMade2": 34, "fieldGoalsMade3": 0,
                               "freeThrowsMade": 0, "valuation": 50}},
        })
        players = {p["person_key"]: p for p in self.season().rows("game_player_stats")}
        self.assertEqual({key: (p["points"], p["payload"]["stats"]["valuation"])
                          for key, p in players.items()},
                         {"A": (20, 15), "B": (60, 40), "C": (70, 50)})
        teams = list(self.season().rows("game_team_stats"))
        self.assertEqual([(t["points"], t["payload"]["total"]["valuation"]) for t in teams],
                         [(80, 55), (70, 50)])
        gaps = list(self.season().rows("game_stat_gaps"))
        self.assertEqual([(g["game_code"], g["stat_name"]) for g in gaps], [(1, "points")])
        self.assertIn("local A 30 -> 20", gaps[0]["reason"])
        self.assertIn("corrected", gaps[0]["reason"])

    def test_points_correction_skips_unproven_games(self):
        def player(code, points, made2, valuation, made3=0):
            stats = {"points": points, "fieldGoalsMade2": made2, "fieldGoalsMade3": made3,
                     "freeThrowsMade": 0, "valuation": valuation, "timePlayed": 600}
            if made3 is None:
                del stats["fieldGoalsMade3"]
            return {"player": {"person": {"code": code, "name": code}, "club": {"code": "MAD"}},
                    "stats": stats}
        def side(players, points):
            return {"players": players, "total": {"points": points, "fieldGoalsMade2": 40,
                                                  "fieldGoalsMade3": 0, "freeThrowsMade": 0}}
        # Each local side's makes add up to 80, which is game 1's score, and its points
        # do not, so only the skip under test keeps the correction from running.
        # Points count as unrecorded only when they are 0 for every player of the game.
        wrong = side([player("A", 30, 10, 25), player("B", 60, 30, 40)], 90)
        road = side([player("C", 70, 35, 50)], 70)
        cases = {
            "points unrecorded": (1, side([player("A", 0, 10, 25), player("B", 0, 30, 40)], 0),
                                  side([player("C", 0, 35, 50)], 0),
                                  {"A": (None, 25), "B": (None, 40)}),
            "no box score": (1, side([], 90), side([], 70), {}),
            "make missing": (1, side([player("A", 30, 10, 25, made3=None),
                                      player("B", 60, 30, 40)], 90),
                             road, {"A": (30, 25), "B": (60, 40)}),
            # The team's makes reach the score but the players' do not: correcting A to 20
            # would leave the players at 70, not 80, so the makes prove nothing.
            "players miss the score": (1, side([player("A", 30, 10, 25), player("B", 50, 25, 40)], 90),
                                       road, {"A": (30, 25), "B": (50, 40)}),
            # The total (95) is not the players' 90, so a corrected total would miss 80.
            "total off its players": (1, side([player("A", 30, 10, 25), player("B", 60, 30, 40)], 95),
                                      road, {"A": (30, 25), "B": (60, 40)}),
            "unplayed": (2, wrong, road, {"A": (30, 25), "B": (60, 40)}),
            "not in games": (3, wrong, road, {"A": (30, 25), "B": (60, 40)}),
        }
        for name, (game, local, road_side, expected) in cases.items():
            with self.subTest(name):
                for old in list((self.root / "bronze").rglob("game_stats")):
                    shutil.rmtree(old)  # one box score per case
                self.write(f"v2/game_stats/{game}.json", {"local": local, "road": road_side})
                players = {p["person_key"]: (p["points"], p["payload"]["stats"]["valuation"])
                           for p in self.season().rows("game_player_stats")
                           if p["person_key"] != "C"}
                self.assertEqual(players, expected)
                gaps = list(self.season().rows("game_stat_gaps"))
                self.assertFalse([g for g in gaps if g["reason"].startswith(CORRECTED_REASON)])
                if name == "no box score":  # the game really has no box score
                    self.assertEqual([g["stat_name"] for g in gaps], ["*"])

    def test_forfeit_without_players_gets_null_team_stats(self):
        self.write("v2/game_stats/2.json", {
            "local": {"players": [], "total": {"points": 0.0, "totalRebounds": 0.0}},
            "road": {"players": [], "total": {"points": 0.0, "totalRebounds": 0.0}},
        })
        teams = [row for row in self.season().rows("game_team_stats") if row["game_code"] == 2]
        self.assertEqual([row["points"] for row in teams], [None, None])
        self.assertEqual([row["payload"]["total"]["totalRebounds"] for row in teams], [None, None])
        gaps = [row for row in self.season().rows("game_stat_gaps") if row["game_code"] == 2]
        self.assertEqual([row["stat_name"] for row in gaps], ["*"])

    def test_game_status_is_derived_and_inferences_are_labelled(self):
        from datetime import datetime, timezone
        from unittest.mock import patch as mock_patch
        import raw_transform
        now = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
        with mock_patch.object(raw_transform, "current_season_year", return_value=2026):
            status = lambda item, season="E2026": raw_transform.game_status(item, season, now)
            self.assertEqual(status({"played": True}), ("completed", None))
            self.assertEqual(status({"played": False, "gameStatus": "Cancelled"})[0], "cancelled")
            self.assertEqual(status({"played": False, "gameStatus": "Confirmed"}, "E2019"),
                             ("cancelled", "not played and the season is over (inferred)"))
            self.assertEqual(status({"played": False, "utcDate": "2026-10-01T10:00:00Z"})[0],
                             "awaiting_result")
            self.assertEqual(status({"played": False, "utcDate": "2026-10-02T18:00:00Z"}),
                             ("scheduled", None))

    def test_zero_attendance_is_null_with_a_note(self):
        from raw_transform import attendance
        self.assertEqual(attendance({"played": True, "audience": 8500}), (8500, None))
        self.assertEqual(attendance({"played": False, "audience": 0}), (None, None))
        self.assertEqual(attendance({"played": True, "audience": 0, "utcDate": "2005-01-12T19:00:00Z"}),
                         (None, "source reported 0: attendance not recorded (or behind closed doors)"))
        self.assertEqual(attendance({"played": True, "audience": 0, "utcDate": "2020-11-05T19:00:00Z"}),
                         (None, "source reported 0: likely behind closed doors (COVID period)"))
        games = {row["game_code"]: row for row in self.season().rows("games")}
        self.assertIsNone(games[2]["audience"])  # unplayed fixture

    def test_old_phase_codes_such_as_top16_are_parsed(self):
        self.write("v3/season_stats/players_misc_TS_perGame.json", {
            "players": [{"player": {"code": "000123", "team": {"code": "MAD"}}}]
        })
        rows = list(self.season().rows("season_player_stats"))
        self.assertEqual([(row["category"], row["phase_code"], row["mode"]) for row in rows],
                         [("misc", "TS", "perGame")])

    def test_team_stats_load_only_the_accumulated_own_feeds(self):
        team = {"code": "MAD", "tvCodes": "RMB", "name": "Real Madrid", "imageUrl": "crest.png"}
        self.write("v3/season_stats/teams_traditional_RS_accumulated.json", {"total": 1, "teams": [
            {"teamRanking": 1, "team": team, "gamesPlayed": 38.0, "pointsScored": 3100.0,
             "twoPointersPercentage": "55.1%", "freeThrowsPercentage": "NaN%"}]})
        self.write("v3/season_stats/teams_opponents_traditional_RS_accumulated.json", {"teams": [
            {"teamRanking": 3, "team": team, "pointsScored": 2900.0}]})
        self.write("v3/season_stats/teams_opponents_advanced_all_perGame.json", {"teams": [
            {"teamRanking": 2, "team": team, "trueShootingPercentage": "59.3%"}]})
        self.write("v3/season_stats/players_traditional_RS_accumulated.json", {"players": [
            {"player": {"code": "000123", "team": {"code": "MAD"}}, "pointsScored": 100}]})
        season = FlatSeason(self.root, "euroleague", "E2025")

        own = list(season.rows("season_team_stats_traditional"))
        self.assertEqual(len(own), 1)
        self.assertEqual((own[0]["phase_code"], own[0]["mode"], own[0]["club_code"],
                          own[0]["club_tv_codes"], own[0]["team_ranking"]),
                         ("RS", "accumulated", "MAD", "RMB", 1))
        self.assertEqual(own[0]["points"], Decimal("3100.0"))
        self.assertEqual(own[0]["two_pointers_percentage"], Decimal("55.1"))
        self.assertIsNone(own[0]["free_throws_percentage"])  # "NaN%": undefined
        # Archived opponents and per-game files are skipped, not loaded.
        self.assertEqual(len(list(season.raw.rows("season_team_stats"))), 1)
        self.assertEqual(list(season.rows("season_team_stats_advanced")), [])
        # The player feeds ignore the team files next to them.
        self.assertEqual([row["person_key"] for row in season.rows("season_player_stats_traditional")],
                         ["000123"])

    def test_unexpected_team_stats_filename_is_refused(self):
        self.write("v3/season_stats/teams_scoring_RS_perGame.json", {"teams": []})
        with self.assertRaisesRegex(ValueError, "Unexpected team stats filename"):
            list(self.season().rows("season_team_stats"))

    def test_people_pages_beyond_the_current_total_are_ignored(self):
        stale = {"person": {"code": "999"}, "club": {"code": "MAD"}, "type": "J"}
        self.write("v2/season_people_pages/offset_001000.json", {"data": [stale], "total": 1001})
        codes = {row["person_key"] for row in self.season().rows("people")}
        self.assertEqual(codes, {"000123"})

    def test_dry_run_checks_keys_without_database(self):
        season = FlatSeason(self.root, "euroleague", "E2025")
        for name in ("seasons", "games", "registrations", "shots"):
            self.assertGreater(FlatDatabaseLoader._dry_run_table(
                season, name, season.files(name), 0), 0)

    def test_schema_is_scoped_and_non_destructive(self):
        for name in TABLES:
            sql = create_table_sql(name)
            self.assertIn('"competition_code"', sql)
            self.assertIn('"season_code"', sql)
            self.assertNotIn("DROP", sql)

    def test_timestamp_casts_share_one_parsing_rule(self):
        from flat_transform import cast
        from raw_transform import parse_source_timestamp
        for raw in ("20250901183000", "2025-09-01T18:30:00", "2025-09-01T20:30:00+02:00"):
            self.assertEqual(cast(raw, "TIMESTAMPTZ"), parse_source_timestamp(raw))

    def test_timestamp_columns_store_zone_aware_dates_as_utc(self):
        from datetime import datetime, timezone
        from flat_transform import cast
        utc = datetime(2025, 9, 1, 10, 0)
        for raw in ("2025-09-01T12:00:00+02:00", "2025-09-01T10:00:00Z", "20250901100000"):
            moment = cast(raw, "TIMESTAMP")
            self.assertEqual((moment, moment.tzinfo), (utc, None), raw)
        self.assertEqual(cast("2025-09-01T12:00:00", "TIMESTAMP NOT NULL"), datetime(2025, 9, 1, 12, 0))
        self.assertEqual(cast("2025-09-01T12:00:00+02:00", "TIMESTAMPTZ"),
                         datetime(2025, 9, 1, 10, 0, tzinfo=timezone.utc))
        self.assertIsNotNone(cast("20250901100000", "TIMESTAMPTZ").tzinfo)

    def load_with_fake_database(self, name):
        """Run _load_table against a fake psycopg2 that marks Json-wrapped values."""
        operations = []

        class Cursor:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def execute(self, sql, params=None):
                operations.append((sql, params))

        class Connection:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def cursor(self):
                return Cursor()

        package = types.ModuleType("psycopg2")
        package.__path__ = []
        extras = types.ModuleType("psycopg2.extras")
        extras.Json = lambda value: ("JSON", value)
        extras.execute_values = lambda cursor, sql, rows, page_size: operations.append(
            (sql, list(rows))
        )
        package.extras = extras
        season = FlatSeason(self.root, "euroleague", "E2025")
        with patch.dict(sys.modules, {"psycopg2": package, "psycopg2.extras": extras}):
            FlatDatabaseLoader._load_table(Connection(), season, name, season.files(name), 0)
        return [row for sql, rows in operations if sql.startswith("INSERT") for row in rows]

    def test_database_writer_replaces_only_selected_season(self):
        operations = []

        class Cursor:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def execute(self, sql, params=None):
                operations.append((sql, params))

        class Connection:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def cursor(self):
                return Cursor()

        package = types.ModuleType("psycopg2")
        package.__path__ = []
        extras = types.ModuleType("psycopg2.extras")
        extras.Json = lambda value: value
        extras.execute_values = lambda cursor, sql, rows, page_size: operations.append(
            (sql, list(rows))
        )
        package.extras = extras
        with patch.dict(sys.modules, {"psycopg2": package, "psycopg2.extras": extras}):
            season = FlatSeason(self.root, "euroleague", "E2025")
            count = FlatDatabaseLoader._load_table(
                Connection(), season, "games", season.files("games"), 0
            )
        self.assertEqual(count, 2)
        deletes = [(sql, params) for sql, params in operations if sql.startswith("DELETE")]
        self.assertEqual(len(deletes), 1)
        self.assertEqual(deletes[0][1], ("E", "E2025"))
        self.assertTrue(any(sql.startswith("INSERT") for sql, _ in operations))


if __name__ == "__main__":
    unittest.main()
