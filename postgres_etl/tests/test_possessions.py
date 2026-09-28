"""Counted possessions: ordering, clock, the possession rules, storage, and CLI wiring."""

import sys
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import possessions
from flat_schema import ADVANCED_TABLES, ALL_TABLES

GAME = {"game_code": 1, "played": True, "local_club_code": "A", "road_club_code": "B"}
ADVANCED = [{"game_code": 1, "side": "local", "possessions": Decimal("70.5")},
            {"game_code": 1, "side": "road", "possessions": Decimal("70.5")}]


def ev(club, kind, marker, ordinal, period="FirstQuarter", minute=1, game=1):
    return {"game_code": game, "period": period, "event_ordinal": ordinal, "club_code": club,
            "play_type": kind, "marker_time": marker, "minute": minute}


def count(events):
    return possessions._count(events, {"A", "B"})


class ClockTests(unittest.TestCase):
    def test_quarters_and_overtimes_become_elapsed_seconds(self):
        self.assertEqual(possessions._clock(ev("A", "2FGM", "09:40", 1)), 20)
        self.assertEqual(possessions._clock(ev("A", "2FGM", "10:00", 1, "ThirdQuarter", 21)),
                         1200)
        self.assertEqual(possessions._clock(ev("A", "2FGM", "00:00", 1, "ForthQuarter", 40)),
                         2400)
        self.assertEqual(possessions._clock(ev("A", "2FGM", "04:30", 1, "ExtraTime", 41)), 2430)
        self.assertEqual(possessions._clock(ev("A", "2FGM", "04:30", 1, "ExtraTime", 46)), 2730)

    def test_missing_or_broken_clock_is_none(self):
        self.assertIsNone(possessions._clock(ev("A", "2FGM", None, 1)))
        self.assertIsNone(possessions._clock(ev("A", "2FGM", "xx", 1)))
        self.assertIsNone(possessions._clock(ev("A", "2FGM", "11:00", 1)))
        self.assertIsNone(possessions._clock(ev("A", "2FGM", "05:00", 1, "Unknown")))


class RuleTests(unittest.TestCase):
    def test_made_shot_ends_a_possession_with_its_length(self):
        result = count([ev("A", "2FGM", "09:40", 1)])
        self.assertEqual(result["A"], {"count": 1, "seconds": Decimal(20), "measured": 1})
        self.assertEqual(result["B"]["count"], 0)

    def test_defensive_rebound_ends_the_missing_teams_possession(self):
        result = count([ev("A", "2FGM", "09:40", 1), ev("B", "2FGA", "09:10", 2),
                        ev("A", "D", "09:08", 3)])
        self.assertEqual(result["B"], {"count": 1, "seconds": Decimal(32), "measured": 1})

    def test_offensive_rebound_keeps_the_same_possession(self):
        result = count([ev("A", "3FGA", "09:50", 1), ev("A", "O", "09:48", 2),
                        ev("A", "TO", "09:30", 3)])
        self.assertEqual(result["A"], {"count": 1, "seconds": Decimal(30), "measured": 1})

    def test_layups_dunks_and_blocked_attempts_are_shots(self):
        result = count([ev("A", "LAYUPMD", "09:40", 1), ev("B", "LAYUPATT", "09:20", 2),
                        ev("A", "D", "09:18", 3), ev("A", "DUNK", "09:00", 4),
                        ev("B", "3FGAB", "08:40", 5), ev("A", "D", "08:38", 6)])
        # A: layup, dunk, and the possession left open at the end of the period.
        self.assertEqual((result["A"]["count"], result["B"]["count"]), (3, 2))

    def test_turnover_ends_a_possession(self):
        result = count([ev("A", "TO", "09:30", 1), ev("B", "2FGM", "09:10", 2)])
        self.assertEqual((result["A"]["count"], result["B"]["count"]), (1, 1))
        self.assertEqual(result["B"]["seconds"], Decimal(20))       # 30 -> 50

    def test_and_one_adds_no_extra_possession(self):
        result = count([ev("A", "2FGM", "09:00", 1), ev("A", "FTM", "09:00", 2),
                        ev("B", "2FGM", "08:40", 3)])
        self.assertEqual((result["A"]["count"], result["B"]["count"]), (1, 1))
        self.assertEqual(result["B"]["seconds"], Decimal(20))       # starts at the free throw

    def test_missed_and_one_rebounded_by_the_shooter_starts_a_new_possession(self):
        result = count([ev("A", "2FGM", "09:00", 1), ev("A", "FTA", "09:00", 2),
                        ev("A", "O", "08:58", 3), ev("A", "TO", "08:40", 4)])
        self.assertEqual(result["A"]["count"], 2)

    def test_trip_ends_on_a_made_last_free_throw_only(self):
        result = count([ev("A", "FTA", "08:00", 1), ev("A", "FTM", "08:00", 2),
                        ev("B", "2FGM", "07:40", 3)])
        self.assertEqual((result["A"]["count"], result["B"]["count"]), (1, 1))
        result = count([ev("A", "FTM", "08:00", 1), ev("A", "FTA", "08:00", 2),
                        ev("B", "D", "07:58", 3)])
        self.assertEqual(result["A"]["count"], 1)                    # ended by the rebound

    def test_missed_last_free_throw_with_an_offensive_rebound_continues(self):
        result = count([ev("A", "FTM", "08:00", 1), ev("A", "FTA", "08:00", 2),
                        ev("A", "O", "07:58", 3), ev("A", "2FGM", "07:50", 4)])
        self.assertEqual(result["A"]["count"], 1)

    def test_events_between_free_throws_do_not_split_a_trip(self):
        result = count([ev("A", "FTM", "08:00", 1), ev("A", "IN", "08:00", 2),
                        ev("A", "TOUT", "08:00", 3), ev("A", "FTM", "08:00", 4)])
        self.assertEqual(result["A"]["count"], 1)

    def test_technical_free_throw_ends_no_possession(self):
        result = count([ev("A", "2FGA", "07:10", 1), ev("A", "CMT", "07:05", 2),
                        ev("B", "FTM", "07:05", 3), ev("A", "2FGM", "07:00", 4)])
        self.assertEqual(result["B"]["count"], 0)
        self.assertEqual(result["A"]["count"], 1)                    # the one possession

    def test_period_end_closes_an_open_possession(self):
        result = count([ev("A", "2FGA", "00:05", 1)])
        self.assertEqual(result["A"], {"count": 1, "seconds": Decimal(600),
                                       "measured": 1})

    def test_overtime_possession_uses_the_overtime_clock(self):
        result = count([ev("A", "2FGM", "04:30", 1, "ExtraTime", 41)])
        self.assertEqual(result["A"]["seconds"], Decimal(30))

    def test_unrecorded_change_of_ball_counts_an_end_for_the_previous_holder(self):
        result = count([ev("A", "2FGA", "09:30", 1), ev("B", "2FGM", "09:10", 2)])
        self.assertEqual((result["A"]["count"], result["B"]["count"]), (1, 1))

    def test_missing_clock_counts_but_has_no_length(self):
        result = count([ev("A", "2FGM", None, 1), ev("B", "TO", None, 2)])
        self.assertEqual(result["A"], {"count": 1, "seconds": Decimal(0), "measured": 0})
        self.assertEqual(result["B"]["count"], 1)

    def test_other_event_types_and_unknown_clubs_are_ignored(self):
        result = count([ev("A", "IN", "10:00", 0), ev("A", "AS", "09:40", 1),
                        ev("ZZZ", "2FGM", "09:40", 2), ev("A", "2FGM", "09:40", 3)])
        self.assertEqual(result["A"]["count"], 1)


class DeriveTests(unittest.TestCase):
    EVENTS = [ev("B", "TO", "08:00", 2, "SecondQuarter", 12), ev("A", "2FGM", "09:40", 1),
              ev("A", "2FGM", "07:30", 3, "SecondQuarter", 12)]

    def test_rows_pair_counted_with_the_estimate_and_sort_events(self):
        rows = possessions.derive_rows([GAME], ADVANCED, self.EVENTS)
        self.assertEqual([(r["side"], r["club_code"], r["opponent_club_code"]) for r in rows],
                         [("local", "A", "B"), ("road", "B", "A")])
        local, road = rows
        self.assertEqual((local["counted_possessions"], road["counted_possessions"]), (2, 1))
        self.assertEqual(local["estimated_possessions"], Decimal("70.5"))
        self.assertEqual(local["possession_seconds"], Decimal("50.000000"))  # 20 + 30
        self.assertEqual(local["avg_possession_seconds"], Decimal("25.000000"))
        self.assertEqual(set(local) | {"competition_code", "season_code"},
                         {field.name for field in ALL_TABLES["game_team_possessions"].fields})

    def test_unplayed_games_and_games_without_events_or_advanced_rows_are_skipped(self):
        played = dict(GAME, game_code=2)
        rows = possessions.derive_rows(
            [dict(GAME, played=False), played, dict(GAME, game_code=3)],
            ADVANCED + [dict(row, game_code=2) for row in ADVANCED[:1]],
            [dict(e, game_code=1) for e in self.EVENTS]
            + [dict(e, game_code=2) for e in self.EVENTS[:1]])
        self.assertEqual(rows, [])

    def test_average_uses_only_measured_possessions(self):
        rows = possessions.derive_rows(
            [GAME], ADVANCED, [ev("A", "2FGM", "09:40", 1), ev("A", "TO", None, 2)])
        self.assertEqual(rows[0]["counted_possessions"], 2)
        self.assertEqual(rows[0]["avg_possession_seconds"], Decimal("20.000000"))

    def test_no_measured_possession_gives_a_null_average(self):
        rows = possessions.derive_rows([GAME], ADVANCED, [ev("A", "2FGM", None, 1)])
        self.assertIsNone(rows[0]["avg_possession_seconds"])

    def test_the_table_is_registered_with_the_advanced_tables(self):
        spec = ADVANCED_TABLES["game_team_possessions"]
        self.assertEqual(spec.key, ("competition_code", "season_code", "game_code", "side"))


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, query, params=None):
        self.connection.operations.append((query, params))
        self.last = query

    def fetchone(self):
        return ("t",) if self.connection.exists else (None,)


class FakeConnection:
    def __init__(self):
        self.operations, self.commits, self.rollbacks, self.exists = [], 0, 0, True

    def __enter__(self):
        return self

    def __exit__(self, kind, *_):
        if kind is None:
            self.commits += 1
        else:
            self.rollbacks += 1
        return False

    def cursor(self):
        return FakeCursor(self)

    def rollback(self):
        pass

    def close(self):
        pass


ROW = {"game_code": 1, "side": "local", "club_code": "A", "opponent_club_code": "B",
       "counted_possessions": 70, "possession_seconds": Decimal("1500"),
       "avg_possession_seconds": Decimal("21.4"), "estimated_possessions": Decimal("70.5")}


class StorageTests(unittest.TestCase):
    def test_replace_is_scoped_and_logged_in_one_transaction(self):
        connection = FakeConnection()
        with patch("psycopg2.extras.execute_values") as insert:
            possessions.replace_season(connection, "E", "E2025", [ROW])
        self.assertEqual((connection.commits, connection.rollbacks), (1, 0))
        deletes = [op for op in connection.operations if op[0].startswith("DELETE")]
        self.assertEqual([op[1] for op in deletes], [("E", "E2025")])
        logs = [op[1] for op in connection.operations if "INSERT INTO" in op[0]]
        self.assertEqual((logs[0][2], logs[0][5]), ("game_team_possessions", 1))
        self.assertEqual(insert.call_args.args[2][0][:4], ("E", "E2025", 1, "local"))

    def test_failure_rolls_back(self):
        connection = FakeConnection()
        with patch("psycopg2.extras.execute_values", side_effect=RuntimeError("copy failed")):
            with self.assertRaises(RuntimeError):
                possessions.replace_season(connection, "E", "E2025", [ROW])
        self.assertEqual((connection.commits, connection.rollbacks), (0, 1))

    def test_read_rows_queries_the_three_silver_tables(self):
        queries = []

        class Cursor:
            description = [("game_code",)]

            def execute(self, query, params=None):
                queries.append(query)

            def fetchall(self):
                return []

        self.assertEqual(possessions.read_rows(Cursor(), "E", "E2025"), [])
        for table in ("games", "game_team_advanced", "play_by_play"):
            self.assertTrue(any(f'"{table}"' in query for query in queries), table)


class RunTests(unittest.TestCase):
    def test_dry_run_never_writes(self):
        with patch.object(possessions, "connect", return_value=FakeConnection()),                 patch.object(possessions, "read_rows", return_value=[ROW]),                 patch.object(possessions, "replace_season") as replace:
            self.assertTrue(possessions.run_seasons("cfg", "euroleague", ["E2025"],
                                                    dry_run=True))
        replace.assert_not_called()

    def test_quality_only_skips_derivation_and_fails_on_errors(self):
        with patch.object(possessions, "connect", return_value=FakeConnection()),                 patch.object(possessions, "read_rows") as read,                 patch.object(possessions, "check_season",
                             return_value=[("ERROR", "x", "t", 2)]):
            self.assertFalse(possessions.run_seasons("cfg", "euroleague", ["E2025"],
                                                     quality_only=True))
        read.assert_not_called()

    def test_warnings_do_not_fail_the_run(self):
        with patch.object(possessions, "connect", return_value=FakeConnection()),                 patch.object(possessions, "read_rows", return_value=[ROW]),                 patch.object(possessions, "replace_season"),                 patch.object(possessions, "check_season",
                             return_value=[("WARN", "counted_far_from_estimate", "t", 3)]):
            self.assertTrue(possessions.run_seasons("cfg", "euroleague", ["E2025"]))


class CheckTests(unittest.TestCase):
    def check(self, stored, fresh, exists=True):
        class Cursor(FakeCursor):
            def fetchone(self):
                return ("t",) if exists else (None,)

        connection = FakeConnection()
        cursor = Cursor(connection)
        connection.cursor = lambda: cursor
        with patch.object(possessions, "read_rows", return_value=fresh),                 patch.object(possessions, "_dict_rows", return_value=stored):
            return possessions.check_season(connection, "E", "E2025")

    def test_matching_rows_report_nothing(self):
        self.assertEqual(self.check([ROW], [dict(ROW)]), [])

    def test_missing_table_keys_and_values_are_errors(self):
        self.assertEqual(self.check([], [], exists=False)[0][1], "missing_table")
        self.assertEqual(self.check([], [ROW])[0][1], "keys_differ_from_derivation")
        changed = dict(ROW, counted_possessions=71)
        self.assertEqual(self.check([changed], [ROW])[0][1], "values_differ_from_derivation")

    def test_counted_far_from_the_estimate_is_a_warning(self):
        far = dict(ROW, counted_possessions=90)
        issues = self.check([far], [dict(far)])
        self.assertEqual([issue[:2] for issue in issues],
                         [("WARN", "counted_far_from_estimate")])
        self.assertEqual(issues[0][3], 1)


class MainWiringTests(unittest.TestCase):
    def run_main(self, argv, result=True):
        import main

        with patch.object(main, "available_seasons", return_value=["E2025"]),                 patch.object(main, "FlatDatabaseLoader"),                 patch.object(main, "validate_loaded", return_value=True),                 patch.object(main, "run_advanced", return_value=True),                 patch.object(main, "run_possessions", return_value=result) as run:
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

    def test_failed_possession_checks_fail_the_load(self):
        code, _ = self.run_main(["-sc", "2025", "-tb", "games"], result=False)
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
