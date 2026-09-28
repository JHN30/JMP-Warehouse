"""Shot splits: flagged points, assisted field goals, storage, checks, and hook wiring."""

import sys
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import shot_splits
from flat_schema import ALL_TABLES
from test_possessions import FakeConnection, FakeCursor

GAME = {"game_code": 1, "played": True, "local_club_code": "A", "road_club_code": "B"}


def shot(club, points, fast=False, second=False, turnover=False, code=None):
    return {"game_code": 1, "club_code": club, "points": points, "fastbreak": fast,
            "second_chance": second, "points_off_turnover": turnover,
            "action_code": code or {0: "2FGA", 1: "FTM", 2: "2FGM", 3: "3FGM"}[points]}


def event(club, kind, marker, ordinal=1, period="FirstQuarter"):
    return {"game_code": 1, "period": period, "event_ordinal": ordinal, "club_code": club,
            "play_type": kind, "marker_time": marker, "minute": 1}


def rows(shots, events):
    return shot_splits.derive_rows([GAME], shots, events)


EVENTS = [event("A", "2FGM", "09:40", 1)]


class PointSplitTests(unittest.TestCase):
    def test_points_of_flagged_made_shots_including_free_throws(self):
        local, road = rows([
            shot("A", 2, fast=True), shot("A", 3, second=True), shot("A", 1, turnover=True),
            shot("A", 2, fast=True, turnover=True), shot("A", 0, fast=True),
            shot("B", 3, fast=True), shot("B", 2)], EVENTS)
        self.assertEqual((local["fast_break_points"], local["second_chance_points"],
                          local["points_off_turnover_points"]), (4, 3, 3))
        self.assertEqual((road["fast_break_points"], road["second_chance_points"],
                          road["points_off_turnover_points"]), (3, 0, 0))

    def test_a_null_flag_makes_the_splits_null_for_both_teams_but_not_the_assists(self):
        broken = shot("A", 2)
        broken["second_chance"] = None
        local, road = rows([broken, shot("B", 3, fast=True)],
                           EVENTS + [event("A", "AS", "09:40", 2)])
        for row in (local, road):
            for column in ("fast_break_points", "second_chance_points",
                           "points_off_turnover_points"):
                self.assertIsNone(row[column])
        self.assertEqual(local["assisted_field_goals"], 1)

    def test_a_game_without_shots_has_null_splits_and_shots_of_unknown_clubs_are_ignored(self):
        local, _ = rows([], EVENTS)
        self.assertIsNone(local["fast_break_points"])
        local, road = rows([shot("ZZZ", 2, fast=True), shot("A", 2, fast=True)], EVENTS)
        self.assertEqual((local["fast_break_points"], road["fast_break_points"]), (2, 0))


class AssistTests(unittest.TestCase):
    def test_assists_count_whatever_their_clock_or_order(self):
        for events in ([event("A", "2FGM", "09:40", 1), event("A", "AS", "09:40", 2)],
                       [event("A", "AS", "09:40", 1), event("A", "2FGM", "09:40", 2)],
                       [event("A", "2FGM", "09:40", 1), event("A", "AS", "05:10", 2)],
                       [event("A", "2FGM", None, 1), event("A", "AS", None, 2)]):
            local, _ = rows([shot("A", 2)], events)
            self.assertEqual((local["field_goals_made"], local["assisted_field_goals"]), (1, 1))
        self.assertEqual(local["assisted_fg_pct"], Decimal("1.000000"))

    def test_two_made_shots_and_one_assist_give_half_assisted(self):
        local, _ = rows([], [event("A", "2FGM", "09:40", 1), event("A", "3FGM", "09:40", 2),
                             event("A", "AS", "09:40", 3)])
        self.assertEqual((local["field_goals_made"], local["assisted_field_goals"]), (2, 1))
        self.assertEqual(local["assisted_fg_pct"], Decimal("0.500000"))

    def test_assists_are_per_club_and_capped_at_the_made_shots(self):
        local, road = rows([], [event("A", "2FGM", "09:40", 1), event("A", "AS", "09:39", 2),
                                event("A", "AS", "09:38", 3), event("B", "AS", "09:40", 4)])
        self.assertEqual(local["assisted_field_goals"], 1)
        self.assertEqual((road["field_goals_made"], road["assisted_field_goals"]), (0, 0))

    def test_layups_and_dunks_are_field_goals(self):
        local, _ = rows([], [event("A", "LAYUPMD", "09:40", 1), event("A", "AS", "09:40", 2),
                             event("A", "DUNK", "09:00", 3)])
        self.assertEqual((local["field_goals_made"], local["assisted_field_goals"]), (2, 1))

    def test_no_made_shots_gives_a_null_percentage(self):
        local, _ = rows([], [event("A", "2FGA", "09:40", 1)])
        self.assertEqual(local["field_goals_made"], 0)
        self.assertIsNone(local["assisted_fg_pct"])


class ShapeTests(unittest.TestCase):
    def test_rows_skip_unplayed_games_and_games_without_events_and_match_the_table(self):
        self.assertEqual(shot_splits.derive_rows([dict(GAME, played=False)], [], EVENTS), [])
        self.assertEqual(shot_splits.derive_rows([GAME], [shot("A", 2)], []), [])
        local, road = rows([shot("A", 2)], EVENTS)
        self.assertEqual((local["side"], road["side"], local["club_code"], road["club_code"]),
                         ("local", "road", "A", "B"))
        self.assertEqual(set(local) | {"competition_code", "season_code"},
                         {field.name for field in ALL_TABLES["game_team_shot_splits"].fields})


ROW = dict(rows([shot("A", 2, fast=True)], EVENTS)[0])


class StorageTests(unittest.TestCase):
    def test_replace_targets_the_splits_table_in_one_transaction(self):
        connection = FakeConnection()
        with patch("psycopg2.extras.execute_values") as insert:
            shot_splits.replace_season(connection, "E", "E2025", [ROW])
        self.assertEqual((connection.commits, connection.rollbacks), (1, 0))
        deletes = [op for op in connection.operations if op[0].startswith("DELETE")]
        self.assertIn('"game_team_shot_splits"', deletes[0][0])
        logs = [op[1] for op in connection.operations if "INSERT INTO" in op[0]]
        self.assertEqual((logs[0][2], logs[0][5]), ("game_team_shot_splits", 1))
        self.assertEqual(insert.call_args.args[2][0][:4], ("E", "E2025", 1, "local"))

    def test_failure_rolls_back(self):
        connection = FakeConnection()
        with patch("psycopg2.extras.execute_values", side_effect=RuntimeError("copy failed")):
            with self.assertRaises(RuntimeError):
                shot_splits.replace_season(connection, "E", "E2025", [ROW])
        self.assertEqual((connection.commits, connection.rollbacks), (0, 1))

    def test_read_rows_queries_the_three_silver_tables(self):
        queries = []

        class Cursor:
            description = [("game_code",)]

            def execute(self, query, params=None):
                queries.append(query)

            def fetchall(self):
                return []

        self.assertEqual(shot_splits.read_rows(Cursor(), "E", "E2025"), [])
        for table in ("games", "shots", "play_by_play"):
            self.assertTrue(any(f'"{table}"' in query for query in queries), table)


class RunAndCheckTests(unittest.TestCase):
    def test_dry_run_never_writes(self):
        with patch("possessions.connect", return_value=FakeConnection()), \
                patch.object(shot_splits, "read_rows", return_value=[ROW]) as read, \
                patch.object(shot_splits, "replace_season") as replace:
            self.assertTrue(shot_splits.run_seasons("cfg", "euroleague", ["E2025"],
                                                    dry_run=True))
        read.assert_called_once()
        replace.assert_not_called()

    def check(self, stored, fresh, assists=0, points=0, exists=True):
        class Cursor(FakeCursor):
            def fetchone(self):
                if "to_regclass" in self.last:
                    return ("t",) if exists else (None,)
                return (assists,) if "assisted_field_goals >" in self.last else (points,)

        connection = FakeConnection()
        cursor = Cursor(connection)
        connection.cursor = lambda: cursor
        with patch.object(shot_splits, "read_rows", return_value=fresh), \
                patch.object(shot_splits, "stored_rows", return_value=stored):
            return shot_splits.check_season(connection, "E", "E2025")

    def test_matching_rows_report_nothing_and_differences_are_errors(self):
        self.assertEqual(self.check([ROW], [dict(ROW)]), [])
        self.assertEqual(self.check([], [], exists=False)[0][1], "missing_table")
        self.assertEqual(self.check([], [ROW])[0][1], "keys_differ_from_derivation")
        self.assertEqual(self.check([dict(ROW, field_goals_made=9)], [ROW])[0][1],
                         "values_differ_from_derivation")

    def test_warnings_for_assists_above_made_and_shot_points_off_the_game_score(self):
        issues = self.check([ROW], [dict(ROW)], assists=2, points=5)
        self.assertEqual([issue[:2] for issue in issues],
                         [("WARN", "assisted_exceeds_made"),
                          ("WARN", "shot_points_differ_from_game")])
        self.assertEqual([issue[3] for issue in issues], [2, 5])


class MainWiringTests(unittest.TestCase):
    def run_main(self, argv, results=(True, True)):
        import main

        with patch.object(main, "available_seasons", return_value=["E2025"]), \
                patch.object(main, "FlatDatabaseLoader"), \
                patch.object(main, "validate_loaded", return_value=True), \
                patch.object(main, "run_advanced", return_value=True), \
                patch.object(main, "run_possessions", return_value=True), \
                patch.object(main, "run_score_flow", return_value=True), \
                patch.object(main, "run_shot_splits", return_value=results[0]) as splits, \
                patch.object(main, "run_shot_zones", return_value=results[1]) as zones:
            return main.main(argv), splits, zones

    def test_both_run_after_a_load_that_includes_shots_or_play_by_play(self):
        for table in ("shots", "play_by_play", "games"):
            with self.subTest(table=table):
                code, splits, zones = self.run_main(["-sc", "2025", "-tb", table])
                self.assertEqual(code, 0)
                splits.assert_called_once()
                zones.assert_called_once()
                self.assertEqual(zones.call_args.args[2], ["E2025"])

    def test_skipped_for_dry_run_quality_only_and_unrelated_tables(self):
        for argv in (["-sc", "2025", "--dry-run"], ["-sc", "2025", "--quality-only"],
                     ["-sc", "2025", "-tb", "clubs"]):
            with self.subTest(argv=argv):
                code, splits, zones = self.run_main(argv)
                self.assertEqual(code, 0)
                splits.assert_not_called()
                zones.assert_not_called()

    def test_a_failed_check_fails_the_load_and_stops_before_the_next_table(self):
        code, splits, zones = self.run_main(["-sc", "2025", "-tb", "shots"],
                                            results=(False, True))
        self.assertEqual(code, 1)
        zones.assert_not_called()
        code, _, _ = self.run_main(["-sc", "2025", "-tb", "shots"], results=(True, False))
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
