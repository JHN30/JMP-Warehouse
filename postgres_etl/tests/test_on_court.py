"""On-court intervals: reconstruction rules, storage, checks, and hook wiring."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import on_court
from flat_schema import ALL_TABLES
from test_possessions import FakeConnection, FakeCursor

GAME = {"game_code": 1, "played": True, "local_club_code": "A", "road_club_code": "B"}
STARTERS = ("a1", "a2", "a3", "a4", "a5")
BENCH = ("a6", "a7")
PLAYERS = ([{"game_code": 1, "side": "local", "person_key": key, "club_code": "A",
             "started": True} for key in STARTERS]
           + [{"game_code": 1, "side": "local", "person_key": key, "club_code": "A",
               "started": False} for key in BENCH]
           + [{"game_code": 1, "side": "road", "person_key": "b1", "club_code": "B",
               "started": True}])


def sub(kind, person, marker, ordinal, period="FirstQuarter", minute=1, club="A"):
    return {"game_code": 1, "period": period, "event_ordinal": ordinal, "club_code": club,
            "person_code": person, "play_type": kind, "marker_time": marker, "minute": minute}


def spans(events, person, game=GAME, side="local"):
    rows = on_court.derive_rows([game], PLAYERS, events)
    return [(r["start_seconds"], r["end_seconds"]) for r in rows
            if r["person_key"] == person and r["side"] == side]


class DeriveTests(unittest.TestCase):
    def test_a_game_without_a_clock_has_no_intervals(self):
        sheet = [sub("2FGM", "a1", "10:00", n) for n in range(20)] + [sub("OUT", "a1", "10:00", 20)]
        self.assertEqual(on_court.derive_rows([GAME], PLAYERS, sheet), [])

    def test_starters_without_substitutions_play_the_whole_game(self):
        self.assertEqual(spans([sub("TO", "a1", "09:00", 1)], "a1"), [(0, 2400)])
        self.assertEqual(spans([sub("TO", "a1", "09:00", 1)], "a6"), [])

    def test_a_swap_splits_and_starts_intervals(self):
        events = [sub("OUT", "a1", "05:00", 1), sub("IN", "a6", "05:00", 2)]
        self.assertEqual(spans(events, "a1"), [(0, 300)])
        self.assertEqual(spans(events, "a6"), [(300, 2400)])

    def test_an_in_before_the_out_at_the_same_instant_gives_the_same_result(self):
        events = [sub("IN", "a6", "05:00", 1), sub("OUT", "a1", "05:00", 2)]
        self.assertEqual(spans(events, "a1"), [(0, 300)])
        self.assertEqual(spans(events, "a6"), [(300, 2400)])

    def test_a_player_out_and_in_at_the_same_instant_keeps_one_interval(self):
        events = [sub("OUT", "a1", "05:00", 1), sub("IN", "a1", "05:00", 2)]
        self.assertEqual(spans(events, "a1"), [(0, 2400)])

    def test_intervals_carry_across_periods_and_count_from_one(self):
        events = [sub("OUT", "a1", "05:00", 1),
                  sub("IN", "a1", "08:00", 2, "SecondQuarter", 11)]
        rows = on_court.derive_rows([GAME], PLAYERS, events)
        mine = [r for r in rows if r["person_key"] == "a1"]
        self.assertEqual([(r["interval_ordinal"], r["start_seconds"], r["end_seconds"])
                          for r in mine], [(1, 0, 300), (2, 720, 2400)])
        self.assertEqual({r["club_code"] for r in mine}, {"A"})

    def test_overtime_extends_the_game_end(self):
        events = [sub("TO", "a1", "02:00", 1, "ExtraTime", 41)]
        self.assertEqual(spans(events, "a1"), [(0, 2700)])
        events = [sub("TO", "a1", "02:00", 1, "ExtraTime", 46)]
        self.assertEqual(spans(events, "a1"), [(0, 3000)])

    def test_trailing_end_of_game_events_without_a_clock_do_not_add_an_overtime(self):
        end = {"game_code": 1, "period": "ExtraTime", "event_ordinal": 9, "club_code": None,
               "person_code": None, "play_type": "EG", "marker_time": None, "minute": 46}
        events = [sub("TO", "a1", "02:00", 1, "ExtraTime", 41), end]
        self.assertEqual(spans(events, "a1"), [(0, 2700)])

    def test_a_period_start_substitution_with_an_out_of_range_clock_uses_the_period_start(self):
        events = [sub("OUT", "a1", "11:00", 1, "ThirdQuarter", 21),
                  sub("IN", "a6", "11:00", 2, "ThirdQuarter", 21)]
        self.assertEqual(spans(events, "a1"), [(0, 1200)])
        self.assertEqual(spans(events, "a6"), [(1200, 2400)])

    def test_a_duplicate_in_and_an_out_for_a_player_not_on_court_are_ignored(self):
        events = [sub("IN", "a1", "09:00", 1), sub("OUT", "a7", "08:00", 2),
                  sub("OUT", "a1", "05:00", 3)]
        self.assertEqual(spans(events, "a1"), [(0, 300)])
        self.assertEqual(spans(events, "a7"), [])

    def test_the_other_clubs_substitutions_do_not_change_this_side(self):
        events = [sub("OUT", "b1", "05:00", 1, club="B")]
        self.assertEqual(spans(events, "b1", side="road"), [(0, 300)])
        self.assertEqual(spans(events, "a1"), [(0, 2400)])

    def test_events_without_a_person_code_are_ignored(self):
        self.assertEqual(spans([sub("OUT", None, "05:00", 1)], "a1"), [(0, 2400)])

    def test_unplayed_and_events_free_games_and_sides_without_a_roster_have_no_rows(self):
        events = [sub("TO", "a1", "09:00", 1)]
        self.assertEqual(on_court.derive_rows([dict(GAME, played=False)], PLAYERS, events), [])
        self.assertEqual(on_court.derive_rows([GAME], PLAYERS, []), [])
        rows = on_court.derive_rows([GAME], PLAYERS[:7], events)
        self.assertEqual({r["side"] for r in rows}, {"local"})

    def test_rows_are_ordered_and_match_the_registered_table(self):
        rows = on_court.derive_rows([GAME], PLAYERS, [sub("OUT", "a1", "05:00", 1)])
        self.assertEqual([r["person_key"] for r in rows[:2]], ["a1", "a2"])
        self.assertEqual(set(rows[0]) | {"competition_code", "season_code"},
                         {field.name for field in ALL_TABLES[on_court.TABLE].fields})


ROW = dict(on_court.derive_rows([GAME], PLAYERS, [sub("TO", "a1", "09:00", 1)])[0])


class StorageTests(unittest.TestCase):
    def test_replace_targets_the_on_court_table_in_one_transaction(self):
        connection = FakeConnection()
        with patch("psycopg2.extras.execute_values") as insert:
            on_court.replace_season(connection, "E", "E2025", [ROW])
        self.assertEqual((connection.commits, connection.rollbacks), (1, 0))
        deletes = [op for op in connection.operations if op[0].startswith("DELETE")]
        self.assertIn('"game_player_on_court"', deletes[0][0])
        self.assertEqual(deletes[0][1], ("E", "E2025"))
        logs = [op[1] for op in connection.operations if "INSERT INTO" in op[0]]
        self.assertEqual((logs[0][2], logs[0][5]), ("game_player_on_court", 1))
        self.assertEqual(insert.call_args.args[2][0][:4], ("E", "E2025", 1, "local"))

    def test_failure_rolls_back(self):
        connection = FakeConnection()
        with patch("psycopg2.extras.execute_values", side_effect=RuntimeError("copy failed")):
            with self.assertRaises(RuntimeError):
                on_court.replace_season(connection, "E", "E2025", [ROW])
        self.assertEqual((connection.commits, connection.rollbacks), (0, 1))

    def test_read_rows_queries_the_three_source_tables(self):
        queries = []

        class Cursor:
            description = [("game_code",)]

            def execute(self, query, params=None):
                queries.append(query)

            def fetchall(self):
                return []

        self.assertEqual(on_court.read_rows(Cursor(), "E", "E2025"), [])
        for table in on_court.SOURCE_TABLES:
            self.assertTrue(any(f'"{table}"' in query for query in queries), table)


class RunTests(unittest.TestCase):
    def test_dry_run_never_writes_and_uses_this_modules_functions(self):
        with patch("possessions.connect", return_value=FakeConnection()), \
                patch.object(on_court, "read_rows", return_value=[ROW]) as read, \
                patch.object(on_court, "replace_season") as replace:
            self.assertTrue(on_court.run_seasons("cfg", "euroleague", ["E2025"], dry_run=True))
        read.assert_called_once()
        replace.assert_not_called()

    def test_quality_only_fails_on_errors_and_warnings_pass(self):
        with patch("possessions.connect", return_value=FakeConnection()), \
                patch.object(on_court, "read_rows") as read, \
                patch.object(on_court, "check_season", return_value=[("ERROR", "x", "t", 1)]):
            self.assertFalse(on_court.run_seasons("cfg", "euroleague", ["E2025"],
                                                  quality_only=True))
        read.assert_not_called()
        with patch("possessions.connect", return_value=FakeConnection()), \
                patch.object(on_court, "check_season", return_value=[("WARN", "w", "t", 1)]):
            self.assertTrue(on_court.run_seasons("cfg", "euroleague", ["E2025"],
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
        with patch.object(on_court, "read_rows", return_value=fresh), \
                patch.object(on_court, "stored_rows", return_value=stored):
            return on_court.check_season(connection, "E", "E2025")

    def test_matching_rows_report_nothing(self):
        self.assertEqual(self.check([ROW], [dict(ROW)]), [])

    def test_missing_table_keys_and_values_are_errors(self):
        self.assertEqual(self.check([], [], exists=False)[0][1], "missing_table")
        self.assertEqual(self.check([], [ROW])[0][1], "keys_differ_from_derivation")
        self.assertEqual(self.check([dict(ROW, end_seconds=9)], [ROW])[0][1],
                         "values_differ_from_derivation")

    def test_players_off_the_box_score_seconds_are_a_warning(self):
        issues = self.check([ROW], [dict(ROW)], differing=3)
        self.assertEqual([issue[:2] for issue in issues],
                         [("WARN", "seconds_differ_from_box_score")])
        self.assertEqual(issues[0][3], 3)


class MainWiringTests(unittest.TestCase):
    def run_main(self, argv, result=True):
        import main

        with patch.object(main, "available_seasons", return_value=["E2025"]), \
                patch.object(main, "FlatDatabaseLoader"), \
                patch.object(main, "validate_loaded", return_value=True), \
                patch.object(main, "run_advanced", return_value=True), \
                patch.object(main, "run_possessions", return_value=True), \
                patch.object(main, "run_score_flow", return_value=True), \
                patch.object(main, "run_shot_splits", return_value=True), \
                patch.object(main, "run_lineups", return_value=True),                 patch.object(main, "run_on_court", return_value=result) as run:
            return main.main(argv), run

    def test_runs_after_a_load_that_includes_a_source_table(self):
        for table in on_court.SOURCE_TABLES:
            with self.subTest(table=table):
                code, run = self.run_main(["-sc", "2025", "-tb", table])
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

    def test_failed_on_court_checks_fail_the_load(self):
        code, _ = self.run_main(["-sc", "2025", "-tb", "games"], result=False)
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
