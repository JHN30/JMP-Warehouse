"""No database required: exercise the coverage status rules, the per-game
scoping quirk, the postseason-series SQL shape, and CLI routing for the
team-season/coverage/postseason-series tables with fakes."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main as etl_main
from aggregates import (
    MEASURE_COLUMNS, POSTSEASON_PHASES, POSTSEASON_SERIES_COLUMNS, TEAM_SEASON_COLUMNS,
    _game_items, _item, _postseason_series_select_sql, _season_counts_sql, _season_items,
    _status, _team_season_stats_select_sql, build_aggregates,
)


class CoverageStatusTests(unittest.TestCase):
    def test_game_status_rules(self):
        self.assertEqual(_status("boxScores", 0, 0), "notYetApplicable")
        self.assertEqual(_status("boxScores", 0, 5), "unavailable")
        self.assertEqual(_status("boxScores", 3, 5), "partial")
        self.assertEqual(_status("boxScores", 5, 5), "available")
        self.assertEqual(_status("boxScores", 7, 5), "available")

    def test_roster_status_rules_use_incomplete_not_partial(self):
        self.assertEqual(_status("rosters", 0, 0), "notYetApplicable")
        self.assertEqual(_status("rosters", 0, 5), "unavailable")
        self.assertEqual(_status("rosters", 3, 5), "incomplete")
        self.assertEqual(_status("rosters", 5, 5), "available")
        for key in ("officialStandings", "rosters", "seasonStatistics"):
            self.assertEqual(_status(key, 3, 5), "incomplete")

    def test_item_shape(self):
        item = _item("boxScores", 3, 5)
        self.assertEqual(item, {
            "key": "boxScores", "label": "Box scores", "status": "partial",
            "availableCount": 3, "applicableCount": 5,
        })

    def test_season_items_order_and_count(self):
        # completed, box, period, clubs_count, standings_clubs, roster_clubs,
        # stats_players, photo_players, shots_games, pbp_games
        counts = (7, 7, 7, 20, 20, 20, 160, 165, 7, 7)
        items = _season_items(counts)
        self.assertEqual([item["key"] for item in items], [
            "boxScores", "periodScores", "officialStandings", "rosters",
            "playerPhotos", "seasonStatistics", "shotLocations", "playByPlay",
        ])
        self.assertEqual(len(items), 8)


class PerGameScopingTests(unittest.TestCase):
    def setUp(self):
        season_items = _season_items((7, 7, 7, 20, 20, 20, 160, 165, 7, 7))
        self.season_by_key = {item["key"]: item for item in season_items}

    def test_played_game_narrows_game_scoped_items(self):
        row = (1, True, True, True, 24, True, True)  # game_code, played, box, period, photo_n, shots, pbp
        game_code, items = _game_items(row, self.season_by_key)
        by_key = {item["key"]: item for item in items}
        self.assertEqual(game_code, 1)
        self.assertEqual(by_key["boxScores"], {
            "key": "boxScores", "label": "Box scores", "status": "available",
            "availableCount": 1, "applicableCount": 1,
        })
        self.assertEqual(by_key["playerPhotos"]["availableCount"], 24)
        self.assertEqual(by_key["playerPhotos"]["applicableCount"], 1)

    def test_unplayed_game_is_not_yet_applicable_for_game_scoped_items(self):
        row = (8, False, False, False, 0, False, False)
        _, items = _game_items(row, self.season_by_key)
        by_key = {item["key"]: item for item in items}
        for key in ("boxScores", "periodScores", "playerPhotos", "shotLocations", "playByPlay"):
            self.assertEqual(by_key[key]["status"], "notYetApplicable")
            self.assertEqual(by_key[key]["availableCount"], 0)
            self.assertEqual(by_key[key]["applicableCount"], 0)

    def test_season_wide_items_are_copied_unchanged_regardless_of_game_state(self):
        played_row = (1, True, True, True, 24, True, True)
        unplayed_row = (8, False, False, False, 0, False, False)
        _, played_items = _game_items(played_row, self.season_by_key)
        _, unplayed_items = _game_items(unplayed_row, self.season_by_key)
        for items in (played_items, unplayed_items):
            by_key = {item["key"]: item for item in items}
            for key in ("officialStandings", "rosters", "seasonStatistics"):
                self.assertEqual(by_key[key], self.season_by_key[key])


class SqlShapeTests(unittest.TestCase):
    def test_team_season_select_pairs_own_and_opponent_by_game_and_opposite_side(self):
        select_sql = _team_season_stats_select_sql()
        self.assertIn("opp.side <> own.side", select_sql)
        self.assertIn("g.played IS TRUE", select_sql)
        self.assertIn("own.stats_kind = 'total'", select_sql)
        for column in MEASURE_COLUMNS:
            self.assertIn(f'sum(own."{column}") AS "own_{column}"', select_sql)
            self.assertIn(f'sum(opp."{column}") AS "opp_{column}"', select_sql)

    def test_team_season_columns_match_own_and_opponent_measures(self):
        expected = {f"own_{c}" for c in MEASURE_COLUMNS} | {f"opp_{c}" for c in MEASURE_COLUMNS}
        self.assertTrue(expected.issubset(set(TEAM_SEASON_COLUMNS)))


class PostseasonSeriesSqlTests(unittest.TestCase):
    """The actual grouping/winner behavior is verified against real E2025
    playoff and play-in data (see the feature spec's Step 2 evidence); these
    tests pin the SQL constructs that behavior depends on, matching this
    module's existing no-database convention (test_quality.py, SqlShapeTests)."""

    def test_only_the_three_postseason_phases_are_included(self):
        sql = _postseason_series_select_sql()
        self.assertEqual(set(POSTSEASON_PHASES), {"PI", "PO", "FF"})
        self.assertIn("phase_code IN ('PI', 'PO', 'FF')", sql)

    def test_pairing_is_symmetric_regardless_of_local_or_road_side(self):
        # LEAST/GREATEST make the pairing key independent of which club was
        # local vs road in any individual game, so a club appearing as local
        # in one game and road in another still collapses into one row.
        sql = _postseason_series_select_sql()
        self.assertIn("LEAST(local_club_code, road_club_code) AS club_a_code", sql)
        self.assertIn("GREATEST(local_club_code, road_club_code) AS club_b_code", sql)
        self.assertIn("GROUP BY competition_code, season_code, phase_code,", sql)
        group_by = sql.split("GROUP BY", 1)[1]
        self.assertIn("LEAST(local_club_code, road_club_code)", group_by)
        self.assertIn("GREATEST(local_club_code, road_club_code)", group_by)

    def test_winner_is_null_on_a_tie_not_defaulted_to_either_club(self):
        sql = _postseason_series_select_sql()
        self.assertIn(
            "CASE WHEN club_a_wins > club_b_wins THEN club_a_code "
            "WHEN club_b_wins > club_a_wins THEN club_b_code ELSE NULL END AS winner_club_code",
            sql,
        )

    def test_wins_are_only_counted_from_played_games(self):
        sql = _postseason_series_select_sql()
        for part in sql.split("count(*) FILTER (WHERE")[1:]:
            self.assertIn("played IS TRUE AND match_winner_club_code", part)
        self.assertIn("LEAST(local_club_code, road_club_code)) AS club_a_wins", sql)
        self.assertIn("GREATEST(local_club_code, road_club_code)) AS club_b_wins", sql)

    def test_every_game_including_unplayed_ones_is_counted_and_listed(self):
        # count(*) (not a played-only filter) drives games_played and the
        # games array, so a scheduled-but-unplayed game still appears (with
        # NULL scores/winner from the games table itself).
        sql = _postseason_series_select_sql()
        self.assertIn("count(*) AS games_played", sql)
        self.assertIn("jsonb_agg(jsonb_build_object(", sql)
        self.assertIn("ORDER BY round_number) AS games", sql)

    def test_postseason_series_columns_include_the_key_and_derived_fields(self):
        self.assertEqual(POSTSEASON_SERIES_COLUMNS, (
            "competition_code", "season_code", "phase_code", "club_a_code", "club_b_code",
            "club_a_name", "club_b_name", "games_played", "club_a_wins", "club_b_wins",
            "winner_club_code", "games",
        ))

    def test_season_counts_select_excludes_unplayed_games_for_game_scoped_counts(self):
        sql = _season_counts_sql()
        self.assertIn("g.played IS TRUE", sql)
        self.assertIn("app_shots", sql)
        self.assertIn("app_play_by_play", sql)


class FakeCursor:
    def __init__(self, count=5, rows=None):
        self.count = count
        self.rows = rows or []
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, query, params=None):
        self.statements.append(query)

    def fetchone(self):
        return (self.count,)

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, count=5, rows=None):
        self.fake_cursor = FakeCursor(count=count, rows=rows)
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

    def commit(self):
        pass

    def close(self):
        pass


class BuildAggregatesTests(unittest.TestCase):
    def test_dry_run_never_deletes_or_inserts(self):
        connection = FakeConnection(count=14, rows=[])
        with patch("aggregates.connect", return_value=connection):
            counts = build_aggregates("unused", ["E2026"], ["app_team_season_stats"], dry_run=True)
        self.assertEqual(counts, {("app_team_season_stats", "E2026"): 14})
        statements = connection.fake_cursor.statements
        self.assertFalse(any("DELETE" in s for s in statements))
        self.assertFalse(any(s.startswith("INSERT") for s in statements))
        self.assertTrue(connection.rolled_back)

    def test_real_run_deletes_the_season_then_inserts(self):
        connection = FakeConnection(count=14, rows=[])
        with patch("aggregates.connect", return_value=connection):
            build_aggregates("unused", ["E2026"], ["app_team_season_stats"], dry_run=False)
        statements = connection.fake_cursor.statements
        delete_index = next(i for i, s in enumerate(statements) if "DELETE FROM" in s)
        insert_index = next(i for i, s in enumerate(statements) if s.startswith("INSERT INTO"))
        self.assertLess(delete_index, insert_index)

    def test_unknown_table_is_rejected(self):
        with self.assertRaises(ValueError):
            build_aggregates("unused", ["E2026"], ["not_an_aggregate_table"])

    def test_postseason_series_dry_run_and_real_run(self):
        connection = FakeConnection(count=10, rows=[])
        with patch("aggregates.connect", return_value=connection):
            counts = build_aggregates("unused", ["E2025"], ["app_postseason_series"], dry_run=True)
        self.assertEqual(counts, {("app_postseason_series", "E2025"): 10})
        self.assertFalse(any(s.startswith("INSERT") for s in connection.fake_cursor.statements))

        connection = FakeConnection(count=10, rows=[])
        with patch("aggregates.connect", return_value=connection):
            build_aggregates("unused", ["E2025"], ["app_postseason_series"], dry_run=False)
        statements = connection.fake_cursor.statements
        delete_index = next(i for i, s in enumerate(statements) if "DELETE FROM" in s)
        insert_index = next(i for i, s in enumerate(statements) if s.startswith("INSERT INTO"))
        self.assertLess(delete_index, insert_index)


class AggregateRoutingTests(unittest.TestCase):
    def test_aggregate_only_selection_skips_the_flat_loader(self):
        with patch.object(etl_main, "available_seasons", return_value=["E2025"]), \
                patch.object(etl_main, "FlatDatabaseLoader") as loader, \
                patch.object(etl_main, "build_aggregates", return_value={}) as build, \
                patch.object(etl_main, "validate_aggregates", return_value=True) as validate:
            self.assertEqual(etl_main.main([
                "-sc", "2025", "-tb", "app_team_season_stats",
            ]), 0)
            loader.return_value.run.assert_not_called()
            build.assert_called_once()
            validate.assert_called_once()

    def test_mixed_selection_runs_flat_records_and_aggregate_paths(self):
        with patch.object(etl_main, "available_seasons", return_value=["E2025"]), \
                patch.object(etl_main, "FlatDatabaseLoader") as loader, \
                patch.object(etl_main, "validate_loaded", return_value=True) as validate_loaded, \
                patch.object(etl_main, "build_aggregates", return_value={}) as build, \
                patch.object(etl_main, "validate_aggregates", return_value=True) as validate_agg:
            self.assertEqual(etl_main.main([
                "-sc", "2025", "-tb", "games", "app_coverage_seasons",
            ]), 0)
            loader.return_value.run.assert_called_once()
            build.assert_called_once()
            validate_loaded.assert_called_once()
            validate_agg.assert_called_once()

    def test_quality_only_does_not_rebuild_aggregates(self):
        with patch.object(etl_main, "available_seasons", return_value=["E2025"]), \
                patch.object(etl_main, "FlatDatabaseLoader") as loader, \
                patch.object(etl_main, "build_aggregates") as build, \
                patch.object(etl_main, "validate_aggregates", return_value=True) as validate:
            self.assertEqual(etl_main.main([
                "-sc", "2025", "-tb", "app_coverage_games", "--quality-only",
            ]), 0)
            loader.return_value.run.assert_not_called()
            build.assert_not_called()
            validate.assert_called_once()


if __name__ == "__main__":
    unittest.main()
