"""No database required: exercise the quality rules with a fake read-only cursor."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from quality import check_season, checks_for_tables
import main as etl_main


class FakeCursor:
    def __init__(self, missing=(), bad_scores=0, mismatches=0):
        self.missing = set(missing)
        self.bad_scores = bad_scores
        self.mismatches = mismatches
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
        if "row.played IS TRUE AND (row.local_score IS NULL" in self.query:
            return (self.bad_scores,)
        if 'FROM "app_games" AS row' in self.query and "AND (" not in self.query:
            return (2,)
        if 'FROM "app_clubs" AS row' in self.query and "AND (" not in self.query:
            return (1,)
        return (0,)


class FakeConnection:
    def __init__(self, **kwargs):
        self.fake_cursor = FakeCursor(**kwargs)

    def cursor(self):
        return self.fake_cursor


class QualityRulesTests(unittest.TestCase):
    def test_partial_stats_feeds_are_warned_for_player_and_team_tables(self):
        for name in ("season_stats_traditional", "season_team_stats_opponents_traditional"):
            checks = [check for check in checks_for_tables(["games", name])
                      if check.code == "season_stats_feed_partial"]
            self.assertEqual([(check.table, check.severity) for check in checks],
                             [(name, "WARN")])
            query = checks[0].query
            self.assertIn("row.phase_code <> 'PS' AND row.mode = 'accumulated'", query)
            self.assertIn("SELECT 'all', count(DISTINCT club_code) FROM played", query)
            self.assertIn("feeds.clubs < expected.clubs", query)
            self.assertEqual(query.count("%s"), 2)
        self.assertNotIn("season_stats_feed_partial",
                         {check.code for check in checks_for_tables(["season_stats_misc"])})

    def test_missing_team_stats_feeds_are_warned_when_games_are_checked(self):
        checks = [(check.code, check.table, check.severity) for check in
                  checks_for_tables(["games", "season_team_stats_opponents_advanced"])]
        self.assertIn(("season_stats_phase_mode_missing", "season_team_stats_opponents_advanced",
                       "WARN"), checks)

    def test_team_points_are_cross_checked_with_the_aggregates(self):
        checks = [check for check in checks_for_tables(["app_team_season_stats"])
                  if check.code == "team_stats_points_mismatch"]
        self.assertEqual(len(checks), 1)
        check = checks[0]
        self.assertEqual((check.table, check.severity), ("season_team_stats_traditional", "WARN"))
        self.assertEqual(check.requires, ("season_team_stats_traditional",
                                          "season_team_stats_opponents_traditional"))
        self.assertIn('"etl_flat_season_team_stats_opponents_traditional"', check.query)
        self.assertIn("mode = 'accumulated'", check.query)
        self.assertEqual(check.query.count("%s"), 2)

    def test_points_mismatch_is_a_warning_and_skipped_without_the_team_tables(self):
        report = check_season(FakeConnection(mismatches=3), "euroleague", "E2025",
                              ["app_team_season_stats"])
        self.assertIn(("WARN", "team_stats_points_mismatch", 3),
                      {(i.severity, i.code, i.count) for i in report.issues})
        self.assertTrue(report.passed)
        connection = FakeConnection(mismatches=3,
                                    missing={"etl_flat_season_team_stats_opponents_traditional"})
        report = check_season(connection, "euroleague", "E2025", ["app_team_season_stats"])
        self.assertNotIn("team_stats_points_mismatch", {i.code for i in report.issues})
        self.assertFalse([q for q in connection.fake_cursor.queries if "agg.own_points" in q])

    def test_missing_season_stats_feeds_are_warned_when_games_are_checked(self):
        checks = [check for check in checks_for_tables(["games", "season_stats_misc"])
                  if check.code == "season_stats_phase_mode_missing"]
        self.assertEqual([(check.table, check.severity) for check in checks],
                         [("season_stats_misc", "WARN")])
        self.assertIn("'all' AS phase_code", checks[0].query)
        self.assertIn("('accumulated'), ('perGame')", checks[0].query)
        self.assertEqual(checks[0].query.count("%s"), 2)  # run with the usual season scope
        alone = {check.code for check in checks_for_tables(["season_stats_misc"])}
        self.assertNotIn("season_stats_phase_mode_missing", alone)

    def test_partial_load_only_checks_its_own_tables(self):
        games_only = checks_for_tables(["games"])
        self.assertEqual({check.code for check in games_only if check.severity == "ERROR"}, {
            "played_missing_score", "played_missing_winner",
            "played_missing_identity", "unplayed_has_result",
        })
        self.assertEqual({(check.code, check.severity) for check in games_only
                          if check.severity != "ERROR"},
                         {("attendance_not_recorded", "WARN"), ("cancelled_inferred", "WARN")})
        self.assertEqual(checks_for_tables(["clubs"]), [])

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

    def test_app_standings_key_parity_is_an_error_when_both_tables_load(self):
        both = {(c.code, c.severity) for c in
                checks_for_tables(["app_standings", "standings_basicstandings"])}
        self.assertIn(("app_standings_key_mismatch", "ERROR"), both)
        alone = {c.code for c in checks_for_tables(["app_standings"])}
        self.assertNotIn("app_standings_key_mismatch", alone)

    def test_bad_played_score_is_an_error(self):
        report = check_season(FakeConnection(bad_scores=1), "euroleague", "E2025",
                              ["games", "clubs"])
        self.assertEqual(report.counts, {"games": 2, "clubs": 1})
        self.assertFalse(report.passed)
        self.assertIn(("ERROR", "played_missing_score", 1),
                      {(i.severity, i.code, i.count) for i in report.issues})

    def test_missing_table_is_reported_without_querying_it(self):
        report = check_season(FakeConnection(missing={"app_clubs"}),
                              "euroleague", "E2025", ["clubs"])
        self.assertFalse(report.passed)
        self.assertEqual(report.counts, {})
        self.assertEqual(report.issues[0].code, "missing_table")

    def test_flat_load_runs_quality_checks_after_loading(self):
        with patch.object(etl_main, "available_seasons", return_value=["E2025"]), \
                patch.object(etl_main, "FlatDatabaseLoader") as loader, \
                patch.object(etl_main, "validate_loaded", return_value=True) as validate:
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
