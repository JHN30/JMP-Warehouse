"""Score flow: lead changes, time, runs, clutch, storage, checks, and hook wiring."""

import sys
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import score_flow
from flat_schema import ALL_TABLES
from test_possessions import FakeConnection, FakeCursor

GAME = {"game_code": 1, "played": True, "local_club_code": "A", "road_club_code": "B"}


def sc(marker, ordinal, a, b, period="FirstQuarter", minute=1, kind="2FGM"):
    return {"game_code": 1, "period": period, "event_ordinal": ordinal, "club_code": "A",
            "play_type": kind, "marker_time": marker, "minute": minute,
            "points_a": a, "points_b": b}


def walk(events):
    return score_flow._walk(sorted(events, key=score_flow._sort_key))


def rows(events):
    return score_flow.derive_rows([GAME], events)


SIMPLE = [sc("09:40", 1, 2, 0), sc("09:00", 2, 2, 3), sc("08:00", 3, 4, 3),
          sc("06:00", 4, 4, 4), sc("05:00", 5, 6, 4)]


class FlowTests(unittest.TestCase):
    def test_lead_changes_ties_time_and_largest_lead(self):
        local, road = rows(SIMPLE)
        self.assertEqual((local["lead_changes"], local["ties"]), (2, 1))
        self.assertEqual((local["points_for"], local["points_against"]), (6, 4))
        # 0-20 tied, 20-60 +2, 60-120 -1, 120-240 +1, 240-300 tied, 300-2400 +2
        self.assertEqual((local["time_leading_seconds"], local["time_trailing_seconds"],
                          local["time_tied_seconds"]), (2260, 60, 80))
        self.assertEqual((road["time_leading_seconds"], road["time_trailing_seconds"]),
                         (60, 2260))
        self.assertEqual((local["largest_lead"], road["largest_lead"]), (2, 1))
        self.assertEqual((road["points_for"], road["lead_changes"]), (4, 2))

    def test_a_direct_lead_change_counts_and_a_tie_in_between_does_not_add_one(self):
        direct = walk([sc("09:00", 1, 2, 0), sc("08:00", 2, 2, 3)])
        self.assertEqual(direct["counts"], {"changes": 1, "ties": 0})
        through_tie = walk([sc("09:00", 1, 2, 0), sc("08:00", 2, 2, 2), sc("07:00", 3, 2, 4)])
        self.assertEqual(through_tie["counts"], {"changes": 1, "ties": 1})
        same_leader = walk([sc("09:00", 1, 2, 0), sc("08:00", 2, 2, 2), sc("07:00", 3, 4, 2)])
        self.assertEqual(same_leader["counts"], {"changes": 0, "ties": 1})

    def test_time_adds_up_to_the_game_length_with_overtime(self):
        flow = walk([sc("09:00", 1, 2, 0), sc("04:30", 2, 2, 3, "ExtraTime", 41)])
        total = flow["seconds"]["a"] + flow["seconds"]["b"] + flow["seconds"]["tied"]
        self.assertEqual(total, 2700)
        self.assertEqual(walk(SIMPLE)["seconds"]["a"] + 60 + 80, 2400)

    def test_trailing_end_of_game_events_without_a_clock_do_not_add_an_overtime(self):
        end = {"game_code": 1, "period": "ExtraTime", "event_ordinal": 9, "club_code": None,
               "play_type": "EG", "marker_time": None, "minute": 46,
               "points_a": None, "points_b": None}
        flow = walk([sc("09:00", 1, 2, 0), sc("04:30", 2, 2, 3, "ExtraTime", 41), end])
        self.assertEqual(sum(flow["seconds"][key] for key in ("a", "b", "tied")), 2700)

    def test_runs_break_on_an_opponent_score_and_cross_periods(self):
        flow = walk([sc("01:00", 1, 3, 0), sc("09:00", 1, 5, 0, "SecondQuarter", 11),
                     sc("08:00", 2, 7, 0, "SecondQuarter", 11),
                     sc("07:00", 3, 7, 2, "SecondQuarter", 11),
                     sc("06:00", 4, 9, 2, "SecondQuarter", 11)])
        self.assertEqual(flow["runs"]["a"], [7, 2])
        self.assertEqual(flow["runs"]["b"], [2])
        local, road = rows([sc("01:00", 1, 3, 0), sc("09:00", 1, 5, 0, "SecondQuarter", 11),
                            sc("08:00", 2, 7, 0, "SecondQuarter", 11),
                            sc("07:00", 3, 7, 2, "SecondQuarter", 11)])
        self.assertEqual((local["longest_run"], local["runs_6_plus"]), (7, 1))
        self.assertEqual((road["longest_run"], road["runs_6_plus"]), (2, 0))

    def test_an_event_that_changes_both_scores_breaks_every_run(self):
        flow = walk([sc("09:00", 1, 2, 0), sc("08:00", 2, 4, 3), sc("07:00", 3, 6, 3)])
        self.assertEqual(flow["runs"]["a"], [2, 2])


class ClutchTests(unittest.TestCase):
    CLOSE = [sc("05:00", 1, 50, 50), sc("04:00", 2, 52, 50, "ForthQuarter", 36),
             sc("02:00", 3, 52, 53, "ForthQuarter", 38)]

    def test_close_game_counts_clutch_seconds_and_points(self):
        local, road = rows(self.CLOSE)
        # margin 0 from 300 to 2160 (only 2100-2160 counts), +2 to 2280, -1 to 2400
        self.assertEqual(local["clutch_seconds"], 300)
        self.assertEqual((local["clutch_points_for"], local["clutch_points_against"]), (2, 3))
        self.assertEqual((road["clutch_points_for"], road["clutch_points_against"]), (3, 2))

    def test_a_blowout_has_no_clutch(self):
        local, _ = rows([sc("05:00", 1, 60, 50), sc("01:00", 2, 62, 50, "ForthQuarter", 39)])
        self.assertEqual((local["clutch_seconds"], local["clutch_points_for"]), (0, 0))

    def test_overtime_is_clutch_while_the_margin_is_within_five(self):
        local, _ = rows([sc("05:00", 1, 50, 50), sc("04:30", 2, 52, 50, "ExtraTime", 41)])
        self.assertEqual(local["clutch_seconds"], 600)      # 2100-2430 tied, 2430-2700 +2
        self.assertEqual(local["clutch_points_for"], 2)


class EdgeTests(unittest.TestCase):
    def test_missing_clock_nulls_the_time_columns_but_keeps_the_counts(self):
        local, _ = rows([sc("09:00", 1, 2, 0), sc(None, 2, 2, 3)])
        self.assertEqual(local["lead_changes"], 1)
        for column in ("time_leading_seconds", "time_trailing_seconds", "time_tied_seconds",
                       "clutch_seconds"):
            self.assertIsNone(local[column])

    def test_a_none_score_value_carries_the_previous_value_forward(self):
        flow = walk([sc("09:00", 1, None, 2), sc("08:00", 2, 2, None)])
        self.assertEqual(flow["points"], {"a": 2, "b": 2})

    def test_events_without_a_score_change_are_ignored(self):
        flow = walk([sc("09:00", 1, 2, 0), sc("08:00", 2, 2, 0), sc("07:00", 3, None, None)])
        self.assertEqual(flow["seconds"]["a"], 2400 - 60)

    def test_a_game_without_scoring_events_has_no_row(self):
        self.assertEqual(rows([sc("09:00", 1, None, None)]), [])
        self.assertEqual(score_flow.derive_rows([dict(GAME, played=False)], SIMPLE), [])
        self.assertEqual(score_flow.derive_rows([GAME], []), [])

    def test_rows_are_ordered_and_match_the_registered_table(self):
        local, road = rows(list(reversed(SIMPLE)))
        self.assertEqual((local["side"], road["side"], local["club_code"], road["club_code"]),
                         ("local", "road", "A", "B"))
        self.assertEqual(set(local) | {"competition_code", "season_code"},
                         {field.name for field in ALL_TABLES["game_team_score_flow"].fields})
        self.assertEqual(local["ties"], road["ties"])


ROW = dict(rows(SIMPLE)[0])


class StorageTests(unittest.TestCase):
    def test_replace_targets_the_score_flow_table_in_one_transaction(self):
        connection = FakeConnection()
        with patch("psycopg2.extras.execute_values") as insert:
            score_flow.replace_season(connection, "E", "E2025", [ROW])
        self.assertEqual((connection.commits, connection.rollbacks), (1, 0))
        deletes = [op for op in connection.operations if op[0].startswith("DELETE")]
        self.assertIn('"game_team_score_flow"', deletes[0][0])
        self.assertEqual(deletes[0][1], ("E", "E2025"))
        logs = [op[1] for op in connection.operations if "INSERT INTO" in op[0]]
        self.assertEqual((logs[0][2], logs[0][5]), ("game_team_score_flow", 1))
        self.assertEqual(insert.call_args.args[2][0][:4], ("E", "E2025", 1, "local"))

    def test_failure_rolls_back(self):
        connection = FakeConnection()
        with patch("psycopg2.extras.execute_values", side_effect=RuntimeError("copy failed")):
            with self.assertRaises(RuntimeError):
                score_flow.replace_season(connection, "E", "E2025", [ROW])
        self.assertEqual((connection.commits, connection.rollbacks), (0, 1))

    def test_read_rows_queries_games_and_play_by_play(self):
        queries = []

        class Cursor:
            description = [("game_code",)]

            def execute(self, query, params=None):
                queries.append(query)

            def fetchall(self):
                return []

        self.assertEqual(score_flow.read_rows(Cursor(), "E", "E2025"), [])
        for table in ("games", "play_by_play"):
            self.assertTrue(any(f'"{table}"' in query for query in queries), table)


class RunTests(unittest.TestCase):
    def test_dry_run_never_writes_and_uses_this_modules_functions(self):
        with patch.object(score_flow, "connect", create=True), \
                patch("possessions.connect", return_value=FakeConnection()), \
                patch.object(score_flow, "read_rows", return_value=[ROW]) as read, \
                patch.object(score_flow, "replace_season") as replace:
            self.assertTrue(score_flow.run_seasons("cfg", "euroleague", ["E2025"],
                                                   dry_run=True))
        read.assert_called_once()
        replace.assert_not_called()

    def test_quality_only_fails_on_errors_and_warnings_pass(self):
        with patch("possessions.connect", return_value=FakeConnection()), \
                patch.object(score_flow, "read_rows") as read, \
                patch.object(score_flow, "check_season", return_value=[("ERROR", "x", "t", 1)]):
            self.assertFalse(score_flow.run_seasons("cfg", "euroleague", ["E2025"],
                                                    quality_only=True))
        read.assert_not_called()
        with patch("possessions.connect", return_value=FakeConnection()), \
                patch.object(score_flow, "check_season", return_value=[("WARN", "w", "t", 1)]):
            self.assertTrue(score_flow.run_seasons("cfg", "euroleague", ["E2025"],
                                                   quality_only=True))


class CheckTests(unittest.TestCase):
    def check(self, stored, fresh, differing=0, exists=True):
        class Cursor(FakeCursor):
            def fetchone(self):
                if "to_regclass" in self.last:
                    return ("t",) if exists else (None,)
                return (differing,)

        connection = FakeConnection()
        cursor = Cursor(connection)
        connection.cursor = lambda: cursor
        with patch.object(score_flow, "read_rows", return_value=fresh), \
                patch.object(score_flow, "stored_rows", return_value=stored):
            return score_flow.check_season(connection, "E", "E2025")

    def test_matching_rows_report_nothing(self):
        self.assertEqual(self.check([ROW], [dict(ROW)]), [])

    def test_missing_table_keys_and_values_are_errors(self):
        self.assertEqual(self.check([], [], exists=False)[0][1], "missing_table")
        self.assertEqual(self.check([], [ROW])[0][1], "keys_differ_from_derivation")
        self.assertEqual(self.check([dict(ROW, ties=9)], [ROW])[0][1],
                         "values_differ_from_derivation")

    def test_final_score_differing_from_the_game_is_a_warning(self):
        issues = self.check([ROW], [dict(ROW)], differing=3)
        self.assertEqual([issue[:2] for issue in issues],
                         [("WARN", "final_score_differs_from_game")])
        self.assertEqual(issues[0][3], 3)


class MainWiringTests(unittest.TestCase):
    def run_main(self, argv, result=True):
        import main

        with patch.object(main, "available_seasons", return_value=["E2025"]), \
                patch.object(main, "FlatDatabaseLoader"), \
                patch.object(main, "validate_loaded", return_value=True), \
                patch.object(main, "run_advanced", return_value=True), \
                patch.object(main, "run_possessions", return_value=True), \
                patch.object(main, "run_shot_splits", return_value=True), \
                patch.object(main, "run_on_court", return_value=True), \
                patch.object(main, "run_lineups", return_value=True), \
                patch.object(main, "run_shot_zones", return_value=True), \
                patch.object(main, "run_score_flow", return_value=result) as run:
            return main.main(argv), run

    def test_runs_after_a_load_that_includes_play_by_play(self):
        code, run = self.run_main(["-sc", "2025", "-tb", "play_by_play"])
        self.assertEqual(code, 0)
        run.assert_called_once()
        self.assertEqual(run.call_args.args[2], ["E2025"])

    def test_skipped_for_dry_run_quality_only_and_unrelated_tables(self):
        for argv in (["-sc", "2025", "--dry-run"], ["-sc", "2025", "--quality-only"],
                     ["-sc", "2025", "-tb", "clubs"]):
            with self.subTest(argv=argv):
                code, run = self.run_main(argv)
                self.assertEqual(code, 0)
                run.assert_not_called()

    def test_failed_score_flow_checks_fail_the_load(self):
        code, _ = self.run_main(["-sc", "2025", "-tb", "games"], result=False)
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
