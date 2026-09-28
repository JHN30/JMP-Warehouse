"""No database required: exercise the quality rules with a fake read-only cursor."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from quality import check_season, checks_for_tables
import main as etl_main


class FakeCursor:
    def __init__(self, missing=(), bad_scores=0, mismatches=0,
                 missing_provenance=0, missing_log=0, load_count_mismatch=0):
        self.missing = set(missing)
        self.bad_scores = bad_scores
        self.mismatches = mismatches
        self.missing_provenance = missing_provenance
        self.missing_log = missing_log
        self.load_count_mismatch = load_count_mismatch
        self.query = ""
        self.params = ()
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, query, params):
        self.query = query
        self.params = params
        self.queries.append(query)

    def fetchone(self):
        if self.query == "SELECT to_regclass(%s)":
            return (None if self.params[0] in self.missing else self.params[0],)
        if "agg.own_points" in self.query:
            return (self.mismatches,)
        if "row.load_id IS NULL OR row.loaded_at IS NULL" in self.query:
            return (self.missing_provenance,)
        if "log.load_id IS NULL OR log.loaded_at <> active.loaded_at" in self.query:
            return (self.missing_log,)
        if "log.row_count <> active.row_count" in self.query:
            return (self.load_count_mismatch,)
        if "row.played IS TRUE AND (row.local_score IS NULL" in self.query:
            return (self.bad_scores,)
        if 'FROM "games" AS row' in self.query and "AND (" not in self.query:
            return (2,)
        if 'FROM "clubs" AS row' in self.query and "AND (" not in self.query:
            return (1,)
        return (0,)


class FakeConnection:
    def __init__(self, **kwargs):
        self.fake_cursor = FakeCursor(**kwargs)

    def cursor(self):
        return self.fake_cursor


class QualityRulesTests(unittest.TestCase):
    def test_partial_stats_feeds_are_warned_for_player_and_team_tables(self):
        for name in ("season_player_stats_traditional", "season_team_stats_opponents_traditional"):
            checks = [check for check in checks_for_tables(["games", name])
                      if check.code == "season_stats_feed_partial"]
            self.assertEqual([(check.table, check.severity) for check in checks],
                             [(name, "WARN")])
            query = checks[0].query
            self.assertIn("row.mode = 'accumulated'", query)
            self.assertIn("SELECT 'all', count(DISTINCT club_code) FROM played", query)
            self.assertIn("feeds.clubs < expected.clubs", query)
            self.assertEqual(query.count("%s"), 2)
        self.assertNotIn("season_stats_feed_partial",
                         {check.code for check in checks_for_tables(["season_player_stats_misc"])})

    def test_missing_team_stats_feeds_are_warned_when_games_are_checked(self):
        checks = [(check.code, check.table, check.severity) for check in
                  checks_for_tables(["games", "season_team_stats_opponents_advanced"])]
        self.assertIn(("season_stats_phase_mode_missing", "season_team_stats_opponents_advanced",
                       "WARN"), checks)

    def test_missing_season_player_stats_feeds_are_warned_when_games_are_checked(self):
        checks = [check for check in checks_for_tables(["games", "season_player_stats_misc"])
                  if check.code == "season_stats_phase_mode_missing"]
        self.assertEqual([(check.table, check.severity) for check in checks],
                         [("season_player_stats_misc", "WARN")])
        self.assertIn("'all' AS phase_code", checks[0].query)
        self.assertIn("('accumulated'), ('perGame')", checks[0].query)
        self.assertEqual(checks[0].query.count("%s"), 2)  # run with the usual season scope
        alone = {check.code for check in checks_for_tables(["season_player_stats_misc"])}
        self.assertNotIn("season_stats_phase_mode_missing", alone)

    def test_partial_load_only_checks_its_own_tables(self):
        games_only = checks_for_tables(["games"])
        self.assertEqual({check.code for check in games_only if check.severity == "ERROR"}, {
            "played_missing_score", "played_missing_winner",
            "played_missing_identity", "unplayed_has_result",
            "missing_provenance", "missing_load_log", "load_count_mismatch",
        })
        self.assertEqual({(check.code, check.severity) for check in games_only
                          if check.severity != "ERROR"},
                         {("attendance_not_recorded", "WARN"), ("cancelled_inferred", "WARN")})
        self.assertEqual({check.code for check in checks_for_tables(["clubs"])},
                         {"missing_provenance", "missing_load_log", "load_count_mismatch"})

    def test_provenance_errors_are_scoped_to_current_rows(self):
        checks = [check for check in checks_for_tables(["games"])
                  if check.code in {"missing_provenance", "missing_load_log",
                                    "load_count_mismatch"}]
        self.assertEqual(len(checks), 3)
        self.assertEqual([check.query.count("%s") for check in checks], [2, 2, 2])
        self.assertIn("row.load_id, row.loaded_at)", checks[1].query)
        self.assertIn("log.table_name = 'games'", checks[1].query)
        self.assertIn("log.row_count <> active.row_count", checks[2].query)
        report = check_season(FakeConnection(missing_provenance=1, missing_log=2,
                                             load_count_mismatch=3),
                              "euroleague", "E2025", ["games"])
        self.assertFalse(report.passed)
        self.assertTrue({("missing_provenance", 1), ("missing_load_log", 2),
                         ("load_count_mismatch", 3)} <=
                        {(issue.code, issue.count) for issue in report.issues})

    def test_missing_load_log_is_an_error_without_querying_it(self):
        connection = FakeConnection(missing={"load_log"})
        report = check_season(connection, "euroleague", "E2025", ["games"])
        self.assertIn(("missing_table", "load_log"),
                      {(issue.code, issue.table) for issue in report.issues})
        self.assertFalse(any('JOIN "load_log"' in query
                             for query in connection.fake_cursor.queries))

    def test_game_children_and_people_are_checked_when_both_sides_are_loaded(self):
        checks = checks_for_tables([
            "games", "clubs", "people", "registrations", "game_player_stats", "shots",
        ])
        self.assertIn(("orphan_game", "shots"), {(c.code, c.table) for c in checks})
        self.assertIn(("orphan_person", "registrations"), {(c.code, c.table) for c in checks})
        self.assertIn(("orphan_club", "game_player_stats"),
                      {(c.code, c.table) for c in checks})
        self.assertNotIn(("orphan_game", "play_by_play"),
                         {(c.code, c.table) for c in checks})
        warnings = {(c.code, c.table) for c in checks if c.severity == "WARN"}
        self.assertIn(("unmatched_live_player", "shots"), warnings)
        self.assertIn(("fallback_person_key", "game_player_stats"), warnings)

    def test_bad_played_score_is_an_error(self):
        report = check_season(FakeConnection(bad_scores=1), "euroleague", "E2025",
                              ["games", "clubs"])
        self.assertEqual(report.counts, {"games": 2, "clubs": 1})
        self.assertFalse(report.passed)
        self.assertIn(("ERROR", "played_missing_score", 1),
                      {(i.severity, i.code, i.count) for i in report.issues})

    def test_missing_table_is_reported_without_querying_it(self):
        report = check_season(FakeConnection(missing={"clubs"}),
                              "euroleague", "E2025", ["clubs"])
        self.assertFalse(report.passed)
        self.assertEqual(report.counts, {})
        self.assertEqual(report.issues[0].code, "missing_table")

    def test_flat_load_runs_quality_checks_after_loading(self):
        with patch.object(etl_main, "available_seasons", return_value=["E2025"]), \
                patch.object(etl_main, "FlatDatabaseLoader") as loader, \
                patch.object(etl_main, "validate_loaded", return_value=True) as validate,                 patch.object(etl_main, "run_advanced", return_value=True),                 patch.object(etl_main, "run_possessions", return_value=True),                 patch.object(etl_main, "run_shot_splits", return_value=True), \
                patch.object(etl_main, "run_shot_zones", return_value=True), \
                patch.object(etl_main, "run_score_flow", return_value=True):
            self.assertEqual(etl_main.main(["-sc", "2025", "-tb", "games"]), 0)
            loader.return_value.run.assert_called_once()
            validate.assert_called_once()

    def test_quality_only_does_not_reload_tables(self):
        with patch.object(etl_main, "available_seasons", return_value=["E2025"]), \
                patch.object(etl_main, "FlatDatabaseLoader") as loader, \
                patch.object(etl_main, "validate_loaded", return_value=True) as validate:
            self.assertEqual(etl_main.main([
                "-sc", "2025", "-tb", "games", "--quality-only"
            ]), 0)
            loader.return_value.run.assert_not_called()
            validate.assert_called_once()


if __name__ == "__main__":
    unittest.main()
