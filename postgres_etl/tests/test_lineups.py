"""Lineup stints: walk, attribution, storage, checks, and hook wiring."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import lineups
from flat_schema import ALL_TABLES
from test_possessions import FakeConnection, FakeCursor

GAME = {"game_code": 1, "played": True, "local_club_code": "A", "road_club_code": "B"}
LOCAL = ("a1", "a2", "a3", "a4", "a5")
ROAD = ("b1", "b2", "b3", "b4", "b5")
PLAYERS = ([{"game_code": 1, "side": "local", "person_key": key, "started": True}
            for key in LOCAL]
           + [{"game_code": 1, "side": "local", "person_key": "a6", "started": False}]
           + [{"game_code": 1, "side": "road", "person_key": key, "started": True}
              for key in ROAD])


def event(kind, club, marker, ordinal, person=None, a=None, b=None,
          period="FirstQuarter", minute=1):
    return {"game_code": 1, "period": period, "event_ordinal": ordinal, "club_code": club,
            "person_code": person, "play_type": kind, "marker_time": marker,
            "minute": minute, "points_a": a, "points_b": b}


def rows(events, players=PLAYERS, game=GAME):
    return lineups.derive_rows([game], players, events)


def local_stints(events, **kwargs):
    return [r for r in rows(events, **kwargs) if r["side"] == "local"]


SIMPLE = [event("2FGM", "A", "09:00", 1, "a1", 2, 0),
          event("OUT", "A", "05:00", 2, "a1"), event("IN", "A", "05:00", 3, "a6"),
          event("2FGM", "B", "04:00", 4, "b1", 2, 2),
          event("3FGM", "A", "03:00", 5, "a2", 5, 2)]


class StintTests(unittest.TestCase):
    def test_a_game_without_substitutions_is_one_stint(self):
        (local,) = local_stints([event("2FGM", "A", "09:00", 1, "a1", 2, 0)])
        self.assertEqual((local["start_seconds"], local["end_seconds"]), (0, 2400))
        self.assertEqual((local["players"], local["opponent_players"]),
                         (",".join(LOCAL), ",".join(ROAD)))
        self.assertEqual((local["possessions_for"], local["possessions_against"]), (1, 0))
        self.assertEqual((local["points_for"], local["points_against"]), (2, 0))

    def test_a_substitution_splits_stints_and_attributes_events_to_the_lineup_on_court(self):
        first, second = local_stints(SIMPLE)
        self.assertEqual((first["start_seconds"], first["end_seconds"]), (0, 300))
        self.assertEqual((second["start_seconds"], second["end_seconds"]), (300, 2400))
        self.assertEqual((first["players"], second["players"]),
                         ("a1,a2,a3,a4,a5", "a2,a3,a4,a5,a6"))
        self.assertEqual((first["possessions_for"], first["points_for"]), (1, 2))
        self.assertEqual((second["possessions_for"], second["possessions_against"]), (1, 1))
        self.assertEqual((second["points_for"], second["points_against"]), (3, 2))
        self.assertEqual((first["stint_ordinal"], second["stint_ordinal"]), (1, 2))

    def test_the_road_row_mirrors_the_local_row(self):
        local = local_stints(SIMPLE)
        road = [r for r in rows(SIMPLE) if r["side"] == "road"]
        for mine, theirs in zip(local, road):
            self.assertEqual((mine["players"], mine["points_for"], mine["possessions_for"]),
                             (theirs["opponent_players"], theirs["points_against"],
                              theirs["possessions_against"]))
            self.assertEqual((theirs["club_code"], theirs["opponent_club_code"]), ("B", "A"))

    def test_the_in_before_the_out_at_one_instant_gives_the_same_stints(self):
        swapped = [SIMPLE[0], SIMPLE[2], SIMPLE[1], *SIMPLE[3:]]
        self.assertEqual(rows(swapped), rows(SIMPLE))

    def test_a_lineup_that_returns_to_the_same_five_players_does_not_split_the_stint(self):
        events = [event("OUT", "A", "05:00", 1, "a1"), event("IN", "A", "05:00", 2, "a1"),
                  event("2FGM", "A", "04:00", 3, "a2", 2, 0)]
        (local,) = local_stints(events)
        self.assertEqual((local["start_seconds"], local["end_seconds"]), (0, 2400))

    def test_stints_carry_across_periods_and_overtime_extends_the_end(self):
        events = [event("2FGM", "A", "09:00", 1, "a1", 2, 0),
                  event("OUT", "A", "08:00", 1, "a1", period="SecondQuarter", minute=11),
                  event("IN", "A", "08:00", 2, "a6", period="SecondQuarter", minute=11),
                  event("2FGM", "A", "02:00", 1, "a2", 4, 0, "ExtraTime", 41)]
        first, second = local_stints(events)
        self.assertEqual((first["end_seconds"], second["start_seconds"]), (720, 720))
        self.assertEqual(second["end_seconds"], 2700)
        self.assertEqual(second["points_for"], 2)

    def test_an_incomplete_lineup_is_left_out(self):
        events = [event("OUT", "A", "05:00", 1, "a1"),
                  event("2FGM", "A", "04:00", 2, "a2", 2, 0),
                  event("IN", "A", "03:00", 3, "a6"),
                  event("2FGM", "A", "02:00", 4, "a2", 4, 0)]
        first, second = local_stints(events)
        self.assertEqual((first["end_seconds"], second["start_seconds"]), (300, 420))
        self.assertEqual(second["players"], "a2,a3,a4,a5,a6")
        self.assertEqual([r["stint_ordinal"] for r in local_stints(events)], [1, 2])

    def test_a_zero_length_stint_without_events_is_dropped(self):
        events = [event("OUT", "A", "10:00", 1, "a1"), event("IN", "A", "10:00", 2, "a6"),
                  event("2FGM", "A", "09:00", 3, "a2", 2, 0)]
        (local,) = local_stints(events)
        self.assertEqual((local["start_seconds"], local["end_seconds"]), (0, 2400))
        self.assertEqual(local["players"], "a2,a3,a4,a5,a6")

    def test_unplayed_and_events_free_games_have_no_rows(self):
        self.assertEqual(rows(SIMPLE, game=dict(GAME, played=False)), [])
        self.assertEqual(rows([]), [])

    def test_rows_match_the_registered_table(self):
        row = rows(SIMPLE)[0]
        self.assertEqual(set(row) | {"competition_code", "season_code"},
                         {field.name for field in ALL_TABLES[lineups.TABLE].fields})


ROW = dict(rows(SIMPLE)[0])


class StorageTests(unittest.TestCase):
    def test_replace_targets_the_stint_table_in_one_transaction(self):
        connection = FakeConnection()
        with patch("psycopg2.extras.execute_values") as insert:
            lineups.replace_season(connection, "E", "E2025", [ROW])
        self.assertEqual((connection.commits, connection.rollbacks), (1, 0))
        deletes = [op for op in connection.operations if op[0].startswith("DELETE")]
        self.assertIn('"game_team_lineup_stints"', deletes[0][0])
        self.assertEqual(deletes[0][1], ("E", "E2025"))
        logs = [op[1] for op in connection.operations if "INSERT INTO" in op[0]]
        self.assertEqual((logs[0][2], logs[0][5]), ("game_team_lineup_stints", 1))
        self.assertEqual(insert.call_args.args[2][0][:5], ("E", "E2025", 1, "local", 1))

    def test_failure_rolls_back(self):
        connection = FakeConnection()
        with patch("psycopg2.extras.execute_values", side_effect=RuntimeError("copy failed")):
            with self.assertRaises(RuntimeError):
                lineups.replace_season(connection, "E", "E2025", [ROW])
        self.assertEqual((connection.commits, connection.rollbacks), (0, 1))

    def test_read_rows_queries_the_three_source_tables(self):
        queries = []

        class Cursor:
            description = [("game_code",)]

            def execute(self, query, params=None):
                queries.append(query)

            def fetchall(self):
                return []

        self.assertEqual(lineups.read_rows(Cursor(), "E", "E2025"), [])
        for table in lineups.SOURCE_TABLES:
            self.assertTrue(any(f'"{table}"' in query for query in queries), table)


class RunTests(unittest.TestCase):
    def test_dry_run_never_writes_and_uses_this_modules_functions(self):
        with patch("possessions.connect", return_value=FakeConnection()), \
                patch.object(lineups, "read_rows", return_value=[ROW]) as read, \
                patch.object(lineups, "replace_season") as replace:
            self.assertTrue(lineups.run_seasons("cfg", "euroleague", ["E2025"], dry_run=True))
        read.assert_called_once()
        replace.assert_not_called()

    def test_quality_only_fails_on_errors_and_warnings_pass(self):
        with patch("possessions.connect", return_value=FakeConnection()), \
                patch.object(lineups, "read_rows") as read, \
                patch.object(lineups, "check_season", return_value=[("ERROR", "x", "t", 1)]):
            self.assertFalse(lineups.run_seasons("cfg", "euroleague", ["E2025"],
                                                 quality_only=True))
        read.assert_not_called()
        with patch("possessions.connect", return_value=FakeConnection()), \
                patch.object(lineups, "check_season", return_value=[("WARN", "w", "t", 1)]):
            self.assertTrue(lineups.run_seasons("cfg", "euroleague", ["E2025"],
                                                quality_only=True))


class CheckTests(unittest.TestCase):
    def check(self, stored, fresh, uncovered=0, exists=True):
        class Cursor(FakeCursor):
            def fetchone(self):
                if "to_regclass" in self.last:
                    return ("t",) if exists else (None,)
                return (uncovered,)

        connection = FakeConnection()
        cursor = Cursor(connection)
        connection.cursor = lambda: cursor
        with patch.object(lineups, "read_rows", return_value=fresh), \
                patch.object(lineups, "stored_rows", return_value=stored):
            return lineups.check_season(connection, "E", "E2025")

    def test_matching_rows_report_nothing(self):
        self.assertEqual(self.check([ROW], [dict(ROW)]), [])

    def test_missing_table_keys_and_values_are_errors(self):
        self.assertEqual(self.check([], [], exists=False)[0][1], "missing_table")
        self.assertEqual(self.check([], [ROW])[0][1], "keys_differ_from_derivation")
        self.assertEqual(self.check([dict(ROW, points_for=9)], [ROW])[0][1],
                         "values_differ_from_derivation")

    def test_a_game_with_little_stint_coverage_is_a_warning(self):
        issues = self.check([ROW], [dict(ROW)], uncovered=2)
        self.assertEqual([issue[:2] for issue in issues],
                         [("WARN", "stints_cover_little_of_the_game")])
        self.assertEqual(issues[0][3], 2)


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
                patch.object(main, "run_on_court", return_value=True), \
                patch.object(main, "run_lineups", return_value=result) as run:
            return main.main(argv), run

    def test_runs_after_a_load_that_includes_a_source_table(self):
        for table in lineups.SOURCE_TABLES:
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

    def test_failed_lineup_checks_fail_the_load(self):
        code, _ = self.run_main(["-sc", "2025", "-tb", "games"], result=False)
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
