"""Shot zones: attempts, makes and points by zone, storage, and checks."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import shot_zones
from flat_schema import ALL_TABLES
from test_possessions import FakeConnection, FakeCursor

GAME = {"game_code": 1, "played": True, "local_club_code": "A", "road_club_code": "B"}
CODES = {0: "2FGA", 2: "2FGM", 3: "3FGM"}


def shot(club, zone, points=0, code=None, game=1):
    return {"game_code": game, "club_code": club, "zone": zone, "points": points,
            "action_code": code or CODES[points]}


class DeriveTests(unittest.TestCase):
    def test_attempts_makes_and_points_per_zone_for_both_teams(self):
        rows = shot_zones.derive_rows([GAME], [
            shot("A", "B", 2), shot("A", "B", 0), shot("A", "C", 3), shot("A", "C", 0),
            shot("A", "C", 0), shot("B", "B", 2), shot("B", "H", 0)])
        self.assertEqual([(r["side"], r["zone"], r["attempts"], r["made"], r["points"])
                          for r in rows],
                         [("local", "B", 2, 1, 2), ("local", "C", 3, 1, 3),
                          ("road", "B", 1, 1, 2), ("road", "H", 1, 0, 0)])
        self.assertEqual({r["club_code"] for r in rows if r["side"] == "road"}, {"B"})

    def test_free_throws_empty_zones_and_unknown_clubs_are_excluded(self):
        rows = shot_zones.derive_rows([GAME], [
            shot("A", "", 2), shot("A", None, 2), shot("A", "B", 1, code="FTM"),
            shot("ZZZ", "B", 2), shot("A", "B", 2)])
        self.assertEqual([(r["zone"], r["attempts"]) for r in rows], [("B", 1)])

    def test_layups_dunks_and_blocked_attempts_are_field_goals(self):
        rows = shot_zones.derive_rows([GAME], [
            shot("A", "B", 2, code="LAYUPMD"), shot("A", "B", 2, code="DUNK"),
            shot("A", "B", 0, code="LAYUPATT"), shot("A", "H", 0, code="3FGAB")])
        self.assertEqual([(r["zone"], r["attempts"], r["made"], r["points"]) for r in rows],
                         [("B", 3, 2, 4), ("H", 1, 0, 0)])

    def test_a_zone_with_only_misses_and_no_zero_rows(self):
        rows = shot_zones.derive_rows([GAME], [shot("A", "D", 0), shot("A", "D", 0)])
        self.assertEqual([(r["zone"], r["attempts"], r["made"], r["points"]) for r in rows],
                         [("D", 2, 0, 0)])

    def test_unplayed_games_games_without_shots_and_order(self):
        self.assertEqual(shot_zones.derive_rows([dict(GAME, played=False)], [shot("A", "B", 2)]),
                         [])
        self.assertEqual(shot_zones.derive_rows([GAME], []), [])
        second = dict(GAME, game_code=2)
        rows = shot_zones.derive_rows([second, GAME], [shot("A", "B", 2, game=2),
                                                        shot("A", "C", 2), shot("A", "A", 2)])
        self.assertEqual([(r["game_code"], r["zone"]) for r in rows],
                         [(1, "A"), (1, "C"), (2, "B")])

    def test_rows_match_the_registered_table(self):
        row = shot_zones.derive_rows([GAME], [shot("A", "B", 2)])[0]
        self.assertEqual(set(row) | {"competition_code", "season_code"},
                         {field.name for field in ALL_TABLES["game_team_shot_zones"].fields})
        self.assertEqual(ALL_TABLES["game_team_shot_zones"].key,
                         ("competition_code", "season_code", "game_code", "side", "zone"))


ROW = dict(shot_zones.derive_rows([GAME], [shot("A", "B", 2)])[0])


class StorageTests(unittest.TestCase):
    def test_replace_targets_the_zones_table_in_one_transaction(self):
        connection = FakeConnection()
        with patch("psycopg2.extras.execute_values") as insert:
            shot_zones.replace_season(connection, "E", "E2025", [ROW])
        self.assertEqual((connection.commits, connection.rollbacks), (1, 0))
        deletes = [op for op in connection.operations if op[0].startswith("DELETE")]
        self.assertIn('"game_team_shot_zones"', deletes[0][0])
        self.assertEqual(insert.call_args.args[2][0][:5], ("E", "E2025", 1, "local", "B"))

    def test_failure_rolls_back(self):
        connection = FakeConnection()
        with patch("psycopg2.extras.execute_values", side_effect=RuntimeError("copy failed")):
            with self.assertRaises(RuntimeError):
                shot_zones.replace_season(connection, "E", "E2025", [ROW])
        self.assertEqual((connection.commits, connection.rollbacks), (0, 1))

    def test_dry_run_never_writes(self):
        with patch("possessions.connect", return_value=FakeConnection()), \
                patch.object(shot_zones, "read_rows", return_value=[ROW]) as read, \
                patch.object(shot_zones, "replace_season") as replace:
            self.assertTrue(shot_zones.run_seasons("cfg", "euroleague", ["E2025"],
                                                   dry_run=True))
        read.assert_called_once()
        replace.assert_not_called()


class CheckTests(unittest.TestCase):
    def check(self, stored, fresh, exists=True):
        class Cursor(FakeCursor):
            def fetchone(self):
                return ("t",) if exists else (None,)

        connection = FakeConnection()
        cursor = Cursor(connection)
        connection.cursor = lambda: cursor
        with patch.object(shot_zones, "read_rows", return_value=fresh), \
                patch.object(shot_zones, "stored_rows", return_value=stored):
            return shot_zones.check_season(connection, "E", "E2025")

    def test_matching_rows_report_nothing(self):
        self.assertEqual(self.check([ROW], [dict(ROW)]), [])

    def test_zone_is_part_of_the_row_key(self):
        other = dict(ROW, zone="C")
        self.assertEqual(self.check([ROW], [ROW, other])[0][1], "keys_differ_from_derivation")
        self.assertEqual(self.check([ROW, other], [ROW, dict(other, attempts=9)])[0][1],
                         "values_differ_from_derivation")

    def test_missing_table_is_an_error(self):
        self.assertEqual(self.check([], [], exists=False)[0][1], "missing_table")


if __name__ == "__main__":
    unittest.main()
