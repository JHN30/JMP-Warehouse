"""Play-by-play aggregates: team totals, storage, and the partition check."""

import unittest
from decimal import Decimal
from unittest.mock import patch

from gold_etl.schema import physical_name
from gold_etl.schema import GOLD_TABLES, PBP_NAMES, ROUND_NAMES, TEAM_PBP_ADDITIVE, columns
from gold_etl.team_pbp import derive_rows, read_silver
from gold_etl.tests.test_team_splits import FakeConnection

D = Decimal


def game(code, phase, local, road):
    return {"game_code": code, "phase_code": phase, "played": True,
            "local_club_code": local, "road_club_code": road}


GAMES = [game(1, "RS", "A", "B"), game(2, "RS", "B", "A"), game(3, "PO", "A", "B")]


def poss(code, club, counted, estimated, seconds, average):
    return {"game_code": code, "club_code": club, "counted_possessions": counted,
            "estimated_possessions": D(str(estimated)), "possession_seconds": D(seconds),
            "avg_possession_seconds": None if average is None else D(average)}


def flow(code, club, changes, ties, times, largest, run, runs6, clutch, clutch_for, clutch_against):
    lead, trail, tied = times if times else (None, None, None)
    return {"game_code": code, "club_code": club, "lead_changes": changes, "ties": ties,
            "time_leading_seconds": lead and D(lead), "time_trailing_seconds": trail and D(trail),
            "time_tied_seconds": tied and D(tied), "largest_lead": largest, "longest_run": run,
            "runs_6_plus": runs6, "clutch_seconds": None if clutch is None else D(clutch),
            "clutch_points_for": clutch_for, "clutch_points_against": clutch_against}


def split(code, club, fast, second, turnover, made, assisted):
    return {"game_code": code, "club_code": club, "fast_break_points": fast,
            "second_chance_points": second, "points_off_turnover_points": turnover,
            "field_goals_made": made, "assisted_field_goals": assisted}


POSSESSIONS = [poss(1, "A", 70, "70.5", 1190, "17"), poss(2, "A", 60, "61", 1200, "20"),
               poss(3, "A", 65, "66", 1105, None),
               poss(1, "B", 71, "70.5", 1207, "17"), poss(2, "B", 68, "69", 1156, "17")]
FLOW = [flow(1, "A", 4, 2, (1200, 1000, 200), 8, 9, 2, 100, 3, 2),
        flow(2, "A", 6, 4, None, 5, 6, 1, None, 1, 1),
        flow(3, "A", 2, 0, (1500, 700, 200), 12, 7, 1, 0, 0, 0)]
SPLITS = [split(1, "A", 10, 8, 12, 30, 18), split(2, "A", None, None, None, 25, 12),
          split(3, "A", 6, 4, 9, 28, 14)]


def pick(rows, scope, club, zone=None):
    return next(row for row in rows if (row["scope"], row["club_code"], row.get("zone"))
                == (scope, club, zone))


class TeamPbpTests(unittest.TestCase):
    rows = derive_rows(GAMES, POSSESSIONS, FLOW, SPLITS)

    def test_all_scope_totals_and_means(self):
        row = pick(self.rows, "all", "A")
        self.assertEqual((row["games"], row["counted_possessions"]), (3, 195))
        self.assertEqual((row["estimated_possessions"], row["possession_seconds"]),
                         (D("197.5"), 3495))
        self.assertEqual(row["avg_possession_seconds"], D("18.384615"))      # (17x70 + 20x60)/130
        self.assertEqual((row["lead_changes_per_game"], row["ties_per_game"]), (4, 2))
        self.assertEqual((row["timed_games"], row["time_leading_seconds"],
                          row["time_trailing_seconds"], row["time_tied_seconds"]),
                         (2, 2700, 1700, 400))
        self.assertEqual((row["largest_lead"], row["longest_run"], row["runs_6_plus"]),
                         (12, 9, 4))
        self.assertEqual((row["clutch_games"], row["clutch_seconds"]), (1, 100))
        self.assertEqual((row["clutch_points_for"], row["clutch_points_against"]), (4, 3))
        self.assertEqual((row["flagged_games"], row["fast_break_points"],
                          row["second_chance_points"], row["points_off_turnover_points"]),
                         (2, 16, 12, 21))
        self.assertEqual((row["field_goals_made"], row["assisted_field_goals"]), (83, 44))
        self.assertEqual(row["assisted_fg_pct"], D("0.530120"))

    def test_phase_and_postseason_scopes(self):
        regular, postseason = pick(self.rows, "RS", "A"), pick(self.rows, "PO", "A")
        self.assertEqual((regular["games"], regular["counted_possessions"]), (2, 130))
        self.assertEqual(regular["avg_possession_seconds"], D("18.384615"))
        self.assertEqual((regular["timed_games"], regular["flagged_games"]), (1, 1))
        self.assertEqual((postseason["games"], postseason["counted_possessions"]), (1, 65))
        self.assertIsNone(postseason["avg_possession_seconds"])     # its only average is NULL
        self.assertEqual(postseason["clutch_games"], 0)             # timed, but no clutch time
        self.assertEqual(postseason["clutch_seconds"], 0)
        self.assertEqual(pick(self.rows, "PS", "A"), dict(postseason, scope="PS"))

    def test_additive_columns_partition_over_the_phases(self):
        whole = pick(self.rows, "all", "A")
        parts = [pick(self.rows, "RS", "A"), pick(self.rows, "PO", "A")]
        for column in TEAM_PBP_ADDITIVE:
            self.assertEqual(whole[column], sum(part[column] or 0 for part in parts), column)

    def test_a_club_missing_from_some_tables_gets_null_columns_not_a_missing_row(self):
        row = pick(self.rows, "all", "B")
        self.assertEqual((row["games"], row["counted_possessions"]), (2, 139))
        self.assertEqual((row["timed_games"], row["flagged_games"]), (0, 0))
        for column in ("lead_changes_per_game", "time_leading_seconds", "largest_lead",
                       "fast_break_points", "field_goals_made", "assisted_fg_pct",
                       "clutch_points_for"):
            self.assertIsNone(row[column], column)
        self.assertEqual([(r["scope"], r["club_code"]) for r in self.rows],
                         sorted((r["scope"], r["club_code"]) for r in self.rows))

    def test_unplayed_games_and_rows_of_unknown_games_are_ignored(self):
        rows = derive_rows([dict(GAMES[0], played=False)], POSSESSIONS, FLOW, SPLITS)
        self.assertEqual(rows, [])
        rows = derive_rows(GAMES[:1], [poss(9, "A", 50, "50", 900, "18")], [], [])
        self.assertEqual(rows, [])

    def test_rows_match_the_registered_table(self):
        row = self.rows[0]
        self.assertEqual(set(row) | {"competition_code", "season_code"},
                         set(columns("team_pbp_stats")))
        self.assertIn("team_pbp_stats", ROUND_NAMES)
        self.assertEqual(PBP_NAMES, ("team_pbp_stats",))
        self.assertNotIn("team_shot_zone_stats", GOLD_TABLES)
        self.assertEqual(GOLD_TABLES["team_pbp_stats"].key,
                         ("competition_code", "season_code", "scope", "club_code"))


class ReadTests(unittest.TestCase):
    def cursor(self, present=True, log=None):
        log = [] if log is None else log

        class Cursor:
            description = [("game_code",)]

            def execute(self, query, params=None):
                log.append(query)
                self.last = query

            def fetchone(self):
                return ("t",) if present else (None,)

            def fetchall(self):
                return []

        return Cursor(), log

    def test_read_silver_fetches_each_table_and_names_a_missing_one(self):
        cursor, log = self.cursor()
        data = read_silver(cursor, "E", "E2025", ("game_team_possessions",))
        self.assertEqual(data, [[], []])
        self.assertTrue(any("silver.games" in q for q in log))
        self.assertTrue(any("silver.game_team_possessions" in q and "SELECT *" in q
                            for q in log))
        cursor, _ = self.cursor(present=False)
        with self.assertRaisesRegex(ValueError, "silver.game_team_score_flow is missing; run "
                                    "python postgres_etl/score_flow.py"):
            read_silver(cursor, "E", "E2025", ("game_team_score_flow",))

    def test_read_rows_dispatch_uses_the_shared_reader(self):
        from gold_etl import team_pbp
        from gold_etl.loader import read_aggregate_rows

        with patch.object(team_pbp, "read_silver",
                          return_value=[GAMES, POSSESSIONS, FLOW, SPLITS]):
            rows = read_aggregate_rows(object(), "team_pbp_stats", "E", "E2025")
        self.assertEqual(rows, derive_rows(GAMES, POSSESSIONS, FLOW, SPLITS))


class StorageTests(unittest.TestCase):
    def test_replace_is_scoped_atomic_and_rolls_back(self):
        from gold_etl.loader import replace_aggregate_scope

        name = "team_pbp_stats"
        stored = dict(derive_rows(GAMES, POSSESSIONS, FLOW, SPLITS)[0],
                      competition_code="E", season_code="E2025")
        db = FakeConnection()
        with patch("gold_etl.loader.read_aggregate_rows", return_value=[stored]), \
                patch("psycopg2.extras.execute_values") as insert:
            self.assertEqual(replace_aggregate_scope(db, name, "E", "E2025"), 1)
        self.assertEqual((db.commits, db.rollbacks), (1, 0))
        self.assertTrue(any(query.startswith(f'DELETE FROM gold."{physical_name(name)}"')
                            and params == ("E", "E2025") for query, params in db.queries))
        self.assertEqual(insert.call_args.args[2][0][:2], ("E", "E2025"))
        failing = FakeConnection()
        with patch("gold_etl.loader.read_aggregate_rows", return_value=[stored]), \
                patch("psycopg2.extras.execute_values", side_effect=RuntimeError("failed")):
            with self.assertRaisesRegex(RuntimeError, "failed"):
                replace_aggregate_scope(failing, name, "E", "E2025")
        self.assertEqual((failing.commits, failing.rollbacks), (0, 1))

    def test_quality_compares_a_fresh_derivation(self):
        from gold_etl.quality import check_aggregate_scope

        expected = dict(derive_rows(GAMES, POSSESSIONS, FLOW, SPLITS)[0],
                        competition_code="E", season_code="E2025")
        db = FakeConnection()
        cursor = db.cursor()
        with patch("gold_etl.quality.read_aggregate_rows", return_value=[expected]):
            for actual, message in (([], "keys differ"),
                                    ([dict(expected, games=99)], "values differ"),
                                    ([expected], None)):
                with patch("gold_etl.quality._dict_rows", return_value=actual):
                    issues = check_aggregate_scope(cursor, "team_pbp_stats", "E", "E2025")
                    self.assertEqual(issues == [], message is None)
                    if message:
                        self.assertIn(message, issues[0])


class PartitionTests(unittest.TestCase):
    def issues(self, name, rows):
        from gold_etl.quality import check_pbp_partition

        with patch("gold_etl.quality._dict_rows", return_value=rows):
            return check_pbp_partition(FakeConnection().cursor(), name, "E", "E2025")

    def stored(self, rows, name="team_pbp_stats"):
        return [dict(row, scope=row["scope"]) for row in rows]

    def test_a_correct_derivation_passes(self):
        self.assertEqual(self.issues("team_pbp_stats",
                                     derive_rows(GAMES, POSSESSIONS, FLOW, SPLITS)), [])

    def test_a_wrong_all_row_or_orphan_phase_rows_are_reported(self):
        rows = derive_rows(GAMES, POSSESSIONS, FLOW, SPLITS)
        broken = [dict(r, counted_possessions=r["counted_possessions"] + 1)
                  if (r["scope"], r["club_code"]) == ("all", "A") else r for r in rows]
        issues = self.issues("team_pbp_stats", broken)
        self.assertEqual(len(issues), 1)
        self.assertIn("counted_possessions of the all scope is not the sum", issues[0])
        no_all = [r for r in rows if r["scope"] != "all"]
        self.assertTrue(any("phase rows without an all row" in i
                            for i in self.issues("team_pbp_stats", no_all)))


if __name__ == "__main__":
    unittest.main()
