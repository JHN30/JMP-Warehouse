"""Per-game advanced stats: formulas, skipped games, storage, and CLI wiring."""

import sys
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import advanced
from flat_schema import ADVANCED_TABLES

LOCAL = dict(points=83, field_goals_made=30, field_goals_attempted=60,
             three_pointers_made=8, three_pointers_attempted=20, free_throws_made=15,
             free_throws_attempted=20, offensive_rebounds=10, defensive_rebounds=25,
             total_rebounds=35, assists=15, steals=6, turnovers=12, blocks=3,
             fouls_committed=18)
ROAD = dict(points=74, field_goals_made=28, field_goals_attempted=62,
            three_pointers_made=6, three_pointers_attempted=18, free_throws_made=12,
            free_throws_attempted=16, offensive_rebounds=9, defensive_rebounds=22,
            total_rebounds=31, assists=12, steals=5, turnovers=10, blocks=2,
            fouls_committed=20)
GAME = {"game_code": 1, "played": True, "phase_code": "RS", "round_number": 3,
        "local_club_code": "AAA", "road_club_code": "BBB"}


def totals(game_code=1, local=LOCAL, road=ROAD):
    return [dict(local, game_code=game_code, side="local", stats_kind="total"),
            dict(road, game_code=game_code, side="road", stats_kind="total"),
            dict(local, game_code=game_code, side="local", stats_kind="team")]


def player(person_key, seconds, side="local", **stats):
    base = dict(points=0, field_goals_made=0, field_goals_attempted=0,
                three_pointers_made=0, three_pointers_attempted=0, free_throws_made=0,
                free_throws_attempted=0, offensive_rebounds=0, defensive_rebounds=0,
                total_rebounds=0, assists=0, steals=0, turnovers=0, blocks=0,
                fouls_committed=0)
    base.update(stats)
    return dict(base, game_code=1, side=side, person_key=person_key, club_code="AAA",
                seconds_played=seconds)


def derive(games=(GAME,), periods=(), team_stats=None, players=(), gaps=()):
    return advanced.derive_rows(list(games), list(periods),
                                totals() if team_stats is None else team_stats,
                                list(players), list(gaps))


class TeamTests(unittest.TestCase):
    def test_formulas_for_a_regulation_game(self):
        team, _ = derive()
        local, road = team
        self.assertEqual((local["club_code"], local["opponent_club_code"]), ("AAA", "BBB"))
        self.assertEqual((local["phase_code"], local["round_number"]), ("RS", 3))
        self.assertEqual(local["game_minutes"], 40)
        self.assertEqual(local["own_possessions_estimate"], Decimal("70.8"))
        self.assertEqual(road["own_possessions_estimate"], Decimal("70.04"))
        self.assertEqual(local["possessions"], Decimal("70.42"))
        self.assertEqual(road["possessions"], Decimal("70.42"))
        self.assertEqual(local["pace"], Decimal("70.42"))
        self.assertAlmostEqual(float(local["offensive_rating"]), 117.86, places=2)
        self.assertAlmostEqual(float(local["defensive_rating"]), 105.08, places=2)
        self.assertEqual(local["net_rating"], local["offensive_rating"] - local["defensive_rating"])
        self.assertEqual(road["offensive_rating"], local["defensive_rating"])
        self.assertEqual(local["efg_pct"], Decimal("0.566667"))     # (30 + 4) / 60
        self.assertEqual(local["opp_efg_pct"], road["efg_pct"])
        self.assertAlmostEqual(float(local["tov_pct"]), 12 / (60 + 8.8 + 12), places=5)
        self.assertEqual(local["orb_pct"], Decimal("0.312500"))     # 10 / (10 + 22)
        self.assertEqual(local["drb_pct"], Decimal("0.735294"))     # 25 / (25 + 9)
        self.assertEqual(local["ft_rate"], Decimal("0.250000"))
        self.assertAlmostEqual(float(local["true_shooting_pct"]), 83 / (2 * 68.8), places=5)
        self.assertEqual(local["assist_ratio"], Decimal("0.500000"))

    def test_overtime_lengthens_the_game(self):
        periods = [{"game_code": 1, "side": side, "period_number": number}
                   for side in ("local", "road") for number in range(1, 6)]
        team, _ = derive(periods=periods)
        self.assertEqual(team[0]["game_minutes"], 45)
        self.assertEqual(team[0]["pace"], (40 * Decimal("70.42") / 45).quantize(advanced.PLACES))

    def test_missing_measure_and_zero_denominator_give_null(self):
        road = dict(ROAD, offensive_rebounds=None, field_goals_attempted=0)
        local, road_row = derive(team_stats=totals(road=road))[0]
        self.assertIsNone(road_row["own_possessions_estimate"])
        self.assertIsNone(local["possessions"])
        self.assertIsNone(local["pace"])
        self.assertIsNone(local["offensive_rating"])
        self.assertIsNone(local["opp_ft_rate"])           # opponent has zero attempts
        self.assertEqual(local["efg_pct"], Decimal("0.566667"))

    def test_games_without_a_full_box_score_are_skipped(self):
        forfeit = dict(GAME, game_code=2)
        unplayed = dict(GAME, game_code=3, played=False)
        half = dict(GAME, game_code=4)
        stats = totals() + totals(2) + totals(3) + totals(4)[:1]
        gaps = [{"game_code": 2, "stat_name": "*"}, {"game_code": 1, "stat_name": "blocks"}]
        team, _ = derive(games=(GAME, forfeit, unplayed, half), team_stats=stats, gaps=gaps)
        self.assertEqual({row["game_code"] for row in team}, {1})


class PlayerTests(unittest.TestCase):
    def test_game_score_and_rates_for_a_player(self):
        star = player("P1", 1200, points=20, field_goals_made=8, field_goals_attempted=15,
                      three_pointers_made=2, three_pointers_attempted=5, free_throws_made=2,
                      free_throws_attempted=4, offensive_rebounds=2, defensive_rebounds=4,
                      total_rebounds=6, assists=5, steals=2, turnovers=3, blocks=1,
                      fouls_committed=2)
        _, rows = derive(players=[star])
        row = rows[0]
        # 20 + 3.2 - 10.5 - 0.8 + 1.4 + 1.2 + 2 + 3.5 + 0.7 - 0.8 - 3
        self.assertEqual(row["game_score"], Decimal("16.9"))
        self.assertEqual(row["seconds_played"], 1200)
        self.assertEqual(row["efg_pct"], Decimal("0.600000"))    # (8 + 1) / 15
        self.assertAlmostEqual(float(row["true_shooting_pct"]), 20 / (2 * 16.76), places=5)
        share = 1200 / 12000                                       # 20 of the team's 200 minutes
        self.assertAlmostEqual(float(row["usage_pct"]),
                               (15 + 0.44 * 4 + 3) / (share * 80.8), places=4)
        self.assertAlmostEqual(float(row["assist_pct"]), 5 / (share * 30 - 8), places=4)
        self.assertAlmostEqual(float(row["orb_pct"]), 2 / (share * (10 + 22)), places=4)
        self.assertAlmostEqual(float(row["drb_pct"]), 4 / (share * (25 + 9)), places=4)
        self.assertAlmostEqual(float(row["trb_pct"]), 6 / (share * (35 + 31)), places=4)
        self.assertAlmostEqual(float(row["steal_pct"]), 2 / (share * 70.42), places=4)
        self.assertAlmostEqual(float(row["block_pct"]), 1 / (share * (62 - 18)), places=4)
        self.assertAlmostEqual(float(row["tov_pct"]), 3 / (15 + 1.76 + 3), places=5)

    def test_zero_minutes_keeps_the_row_without_rates(self):
        bench = player("P2", 0, side="road", turnovers=1)
        _, rows = derive(players=[bench])
        row = rows[0]
        self.assertEqual(row["side"], "road")
        self.assertEqual(row["game_score"], Decimal("-1.0"))
        for column in ("usage_pct", "assist_pct", "orb_pct", "trb_pct", "steal_pct", "block_pct"):
            self.assertIsNone(row[column], column)

    def test_rates_use_the_official_team_total_not_the_player_sum(self):
        row = derive(players=[player("P3", 2400, assists=4, field_goals_made=1)])[1][0]
        # Player sum (1 FGM) disagrees with the team total (30 FGM); the total is used.
        self.assertAlmostEqual(float(row["assist_pct"]), 4 / (0.2 * 30 - 1), places=4)


class FakeCursor:
    def __init__(self, operations):
        self.operations = operations

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, query, params=None):
        self.operations.append((query, params))


class FakeConnection:
    def __init__(self):
        self.operations, self.commits, self.rollbacks = [], 0, 0

    def __enter__(self):
        return self

    def __exit__(self, kind, *_):
        if kind is None:
            self.commits += 1
        else:
            self.rollbacks += 1
        return False

    def cursor(self):
        return FakeCursor(self.operations)

    def rollback(self):
        pass

    def close(self):
        pass


class StorageTests(unittest.TestCase):
    rows = ([{field.name: 1 for field in ADVANCED_TABLES["game_team_advanced"].fields}],
            [{field.name: 1 for field in ADVANCED_TABLES["game_player_advanced"].fields}])

    def test_replace_is_scoped_and_logged_in_one_transaction(self):
        connection = FakeConnection()
        with patch("psycopg2.extras.execute_values") as insert:
            advanced.replace_season(connection, "E", "E2025", *self.rows)
        self.assertEqual((connection.commits, connection.rollbacks), (1, 0))
        deletes = [op for op in connection.operations if op[0].startswith("DELETE")]
        self.assertEqual([op[1] for op in deletes], [("E", "E2025")] * 2)
        self.assertEqual(insert.call_count, 2)
        logs = [op[1] for op in connection.operations if "INSERT INTO" in op[0]]
        self.assertEqual([entry[2] for entry in logs],
                         ["game_team_advanced", "game_player_advanced"])
        self.assertEqual([entry[5] for entry in logs], [1, 1])
        self.assertEqual(insert.call_args_list[0].args[2][0][:2], ("E", "E2025"))

    def test_failure_rolls_back(self):
        connection = FakeConnection()
        with patch("psycopg2.extras.execute_values", side_effect=RuntimeError("copy failed")):
            with self.assertRaises(RuntimeError):
                advanced.replace_season(connection, "E", "E2025", *self.rows)
        self.assertEqual((connection.commits, connection.rollbacks), (0, 1))


class RunTests(unittest.TestCase):
    def test_dry_run_never_writes(self):
        with patch.object(advanced, "connect", return_value=FakeConnection()), \
                patch.object(advanced, "read_rows", return_value=([{}], [{}, {}])), \
                patch.object(advanced, "replace_season") as replace:
            self.assertTrue(advanced.run_seasons("cfg", "euroleague", ["E2025"], dry_run=True))
        replace.assert_not_called()

    def test_quality_only_skips_derivation_and_fails_on_errors(self):
        with patch.object(advanced, "connect", return_value=FakeConnection()), \
                patch.object(advanced, "read_rows") as read, \
                patch.object(advanced, "check_season", return_value=[("ERROR", "x", "t", 2)]):
            self.assertFalse(advanced.run_seasons("cfg", "euroleague", ["E2025"],
                                                  quality_only=True))
        read.assert_not_called()

    def test_check_season_reports_counts_and_missing_tables(self):
        class Cursor(FakeCursor):
            exists = True

            def execute(self, query, params=None):
                self.last = query

            def fetchone(self):
                if "to_regclass" in self.last:
                    return ("t",) if self.exists else (None,)
                return (2,)

        cursor = Cursor([])
        connection = type("C", (), {"cursor": lambda self: cursor})()
        issues = advanced.check_season(connection, "E", "E2025")
        self.assertEqual([issue[1] for issue in issues],
                         ["missing_team_rows", "missing_player_rows",
                          "possessions_differ_between_sides", "implausible_pace_or_rating"])
        self.assertTrue(all(issue[3] == 2 for issue in issues))
        cursor.exists = False
        self.assertEqual({issue[1] for issue in advanced.check_season(connection, "E", "E2025")},
                         {"missing_table"})


class MainWiringTests(unittest.TestCase):
    def run_main(self, argv, advanced_result=True):
        import main

        with patch.object(main, "available_seasons", return_value=["E2025"]),                 patch.object(main, "FlatDatabaseLoader"),                 patch.object(main, "validate_loaded", return_value=True),                 patch.object(main, "run_advanced", return_value=advanced_result) as run:
            return main.main(argv), run

    def test_runs_after_a_load_that_includes_game_tables(self):
        code, run = self.run_main(["-sc", "2025", "-tb", "game_team_stats"])
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

    def test_failed_advanced_checks_fail_the_load(self):
        code, _ = self.run_main(["-sc", "2025"], advanced_result=False)
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
