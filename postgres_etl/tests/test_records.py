"""No database required: exercise the ranking SQL, validation rules, and CLI
routing for the all-time records tables with fakes."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main as etl_main
from records import (
    PLAYER_SEASON_METRICS, SINGLE_GAME_METRICS, TEAM_SEASON_METRICS, TOP_N,
    _player_season_select, _single_game_select, _team_season_select,
    build_records, validate_records,
)


class RankingSqlTests(unittest.TestCase):
    def test_player_season_select_covers_every_metric_with_one_param_each(self):
        select_sql, params = _player_season_select()
        for metric in PLAYER_SEASON_METRICS:
            self.assertIn(f"'{metric}' AS metric", select_sql)
        self.assertEqual(params, ("E",) * len(PLAYER_SEASON_METRICS))
        self.assertIn(f"rank_ordinal <= {TOP_N}", select_sql)

    def test_player_season_select_has_no_forfeit_filter(self):
        # season_stats_traditional is already a season aggregate from the
        # source API; forfeit exclusion only applies at the game-level tables.
        select_sql, _ = _player_season_select()
        self.assertNotIn("played", select_sql)

    def test_player_season_tie_break_is_season_then_person(self):
        select_sql, _ = _player_season_select()
        self.assertIn("season_code ASC, person_key ASC", select_sql)

    def test_single_game_select_excludes_unplayed_games(self):
        select_sql, params = _single_game_select()
        self.assertIn("g.played IS TRUE", select_sql)
        self.assertEqual(params, ("E",) * len(SINGLE_GAME_METRICS))

    def test_single_game_tie_break_is_season_game_then_person(self):
        select_sql, _ = _single_game_select()
        self.assertIn("gps.season_code ASC, gps.game_code ASC, gps.person_key ASC", select_sql)

    def test_team_season_select_sums_per_club_from_total_stats_and_excludes_unplayed(self):
        select_sql, params = _team_season_select()
        self.assertIn("gts.stats_kind = 'total'", select_sql)
        self.assertIn("g.played IS TRUE", select_sql)
        self.assertIn("sum(gts.", select_sql)
        self.assertEqual(params, ("E",) * len(TEAM_SEASON_METRICS))

    def test_team_season_tie_break_is_season_then_club(self):
        select_sql, _ = _team_season_select()
        self.assertIn("season_code ASC, club_code ASC", select_sql)


class FakeCursor:
    def __init__(self, count=5):
        self.count = count
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, query, params=None):
        self.statements.append(query)

    def fetchone(self):
        return (self.count,)


class FakeConnection:
    def __init__(self, count=5):
        self.fake_cursor = FakeCursor(count=count)
        self.rolled_back = False

    def cursor(self):
        return self.fake_cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, *_):
        return False

    def set_session(self, **kwargs):
        pass

    def rollback(self):
        self.rolled_back = True

    def close(self):
        pass


class BuildRecordsTests(unittest.TestCase):
    def test_dry_run_never_truncates_or_inserts_and_reads_readonly(self):
        connection = FakeConnection(count=42)
        with patch("records.connect", return_value=connection):
            counts = build_records("unused", ["app_records_player_seasons"], dry_run=True)
        self.assertEqual(counts, {"app_records_player_seasons": 42})
        statements = connection.fake_cursor.statements
        self.assertFalse(any("TRUNCATE" in s for s in statements))
        self.assertFalse(any(s.startswith("INSERT") for s in statements))
        self.assertTrue(connection.rolled_back)

    def test_real_run_truncates_then_inserts_then_counts(self):
        connection = FakeConnection(count=50)
        with patch("records.connect", return_value=connection):
            counts = build_records("unused", ["app_records_team_seasons"], dry_run=False)
        statements = connection.fake_cursor.statements
        truncate_index = next(i for i, s in enumerate(statements) if "TRUNCATE TABLE" in s)
        insert_index = next(i for i, s in enumerate(statements) if s.startswith("INSERT INTO"))
        self.assertLess(truncate_index, insert_index)
        self.assertEqual(counts, {"app_records_team_seasons": 50})

    def test_unknown_table_is_rejected(self):
        with self.assertRaises(ValueError):
            build_records("unused", ["not_a_records_table"])


class SequentialCursor:
    def __init__(self, results):
        self.results = list(results)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, query, params=None):
        pass

    def fetchone(self):
        return self.results.pop(0)


class SequentialConnection:
    def __init__(self, results):
        self.fake_cursor = SequentialCursor(results)

    def cursor(self):
        return self.fake_cursor

    def set_session(self, **kwargs):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


class ValidateRecordsTests(unittest.TestCase):
    def test_clean_table_passes(self):
        # to_regclass, total count, bad_value count, oversized count, bad_ranks count
        results = [("app_records_player_seasons",), (200,), (0,), (0,), (0,)]
        with patch("records.connect", return_value=SequentialConnection(results)):
            self.assertTrue(validate_records("unused", ["app_records_player_seasons"]))

    def test_missing_table_fails(self):
        with patch("records.connect", return_value=SequentialConnection([(None,)])):
            self.assertFalse(validate_records("unused", ["app_records_player_seasons"]))

    def test_null_or_negative_value_fails(self):
        results = [("x",), (200,), (1,), (0,), (0,)]
        with patch("records.connect", return_value=SequentialConnection(results)):
            self.assertFalse(validate_records("unused", ["app_records_player_seasons"]))

    def test_metric_over_top_n_rows_fails(self):
        results = [("x",), (200,), (0,), (1,), (0,)]
        with patch("records.connect", return_value=SequentialConnection(results)):
            self.assertFalse(validate_records("unused", ["app_records_player_seasons"]))

    def test_rank_ordinal_not_dense_fails(self):
        results = [("x",), (200,), (0,), (0,), (1,)]
        with patch("records.connect", return_value=SequentialConnection(results)):
            self.assertFalse(validate_records("unused", ["app_records_player_seasons"]))


class RecordsRoutingTests(unittest.TestCase):
    def test_records_only_selection_skips_the_flat_loader(self):
        with patch.object(etl_main, "available_seasons", return_value=["E2025"]), \
                patch.object(etl_main, "FlatDatabaseLoader") as loader, \
                patch.object(etl_main, "build_records", return_value={}) as build, \
                patch.object(etl_main, "validate_records", return_value=True) as validate:
            self.assertEqual(etl_main.main([
                "-sc", "2025", "-tb", "app_records_player_seasons",
            ]), 0)
            loader.return_value.run.assert_not_called()
            build.assert_called_once()
            validate.assert_called_once()

    def test_mixed_selection_runs_both_the_flat_loader_and_records(self):
        with patch.object(etl_main, "available_seasons", return_value=["E2025"]), \
                patch.object(etl_main, "FlatDatabaseLoader") as loader, \
                patch.object(etl_main, "validate_loaded", return_value=True) as validate_loaded, \
                patch.object(etl_main, "build_records", return_value={}) as build, \
                patch.object(etl_main, "validate_records", return_value=True) as validate_records_mock:
            self.assertEqual(etl_main.main([
                "-sc", "2025", "-tb", "games", "app_records_player_seasons",
            ]), 0)
            loader.return_value.run.assert_called_once()
            build.assert_called_once()
            validate_loaded.assert_called_once()
            validate_records_mock.assert_called_once()

    def test_quality_only_does_not_rebuild_records(self):
        with patch.object(etl_main, "available_seasons", return_value=["E2025"]), \
                patch.object(etl_main, "FlatDatabaseLoader") as loader, \
                patch.object(etl_main, "build_records") as build, \
                patch.object(etl_main, "validate_records", return_value=True) as validate:
            self.assertEqual(etl_main.main([
                "-sc", "2025", "-tb", "app_records_player_seasons", "--quality-only",
            ]), 0)
            loader.return_value.run.assert_not_called()
            build.assert_not_called()
            validate.assert_called_once()


if __name__ == "__main__":
    unittest.main()
