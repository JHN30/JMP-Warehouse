"""Postseason pairing rules and transactional storage."""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from gold_etl.loader import replace_series_scope
from gold_etl.series import derive_rows


def game(code, phase="PO", local="A", road="B", winner=None, played=True, round_no=1,
         score=(80, 70), status="completed"):
    return {"game_code": code, "phase_code": phase, "round_number": round_no,
            "scheduled_at": datetime(2025, 4, 1, 22, tzinfo=timezone(timedelta(hours=2))),
            "local_club_code": local, "road_club_code": road,
            "local_club_name": local, "road_club_name": road,
            "played": played, "local_score": score[0] if played else None,
            "road_score": score[1] if played else None,
            "match_winner_club_code": winner, "status": status}


def leg(code, local, road, local_score, road_score, phase="8F", played=True):
    winner = (None if not played or local_score == road_score else
              local if local_score > road_score else road)
    return game(code, phase, local, road, winner, played, code, (local_score, road_score))


class DerivationTests(unittest.TestCase):
    def test_reversed_pairing_tie_and_scheduled_game(self):
        rows = derive_rows([game(3, local="B", road="A", played=False, round_no=2),
                            game(2, local="B", road="A", winner="B"),
                            game(1, local="A", road="B", winner="A")])
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual((row["club_a_code"], row["club_b_code"]), ("A", "B"))
        self.assertEqual((row["games_played"], row["club_a_wins"],
                          row["club_b_wins"], row["winner_club_code"]), (3, 1, 1, None))
        self.assertEqual([item["gameCode"] for item in row["games"]], [1, 2, 3])
        self.assertEqual(row["games"][0]["scheduledAt"], "2025-04-01T20:00:00.000Z")
        self.assertIsNone(row["games"][-1]["localScore"])
        self.assertIsNone(row["games"][-1]["roadScore"])
        self.assertIsNone(row["games"][-1]["winnerClubCode"])

    def test_play_in_and_final_four_are_separate_and_top_16_excluded(self):
        rows = derive_rows([game(1, "PI", "A", "B", "A"),
                            game(2, "PI", "B", "C", "C"),
                            game(3, "PI", "A", "C", "C"),
                            game(4, "FF", "A", "B", "B"),
                            game(5, "TS", "A", "B", "A")])
        self.assertEqual(len(rows), 4)
        self.assertEqual(sum(row["phase_code"] == "PI" for row in rows), 3)
        self.assertTrue(all(row["games_played"] == 1 for row in rows))
        self.assertEqual(next(row for row in rows if row["phase_code"] == "FF")
                         ["winner_club_code"], "B")

    def test_two_leg_tie_is_won_on_aggregate(self):
        split = [leg(1, "A", "B", 80, 70), leg(2, "B", "A", 85, 72)]  # 1-1, B 155-152
        row = derive_rows(split, "U2015")[0]
        self.assertEqual((row["club_a_wins"], row["club_b_wins"], row["winner_club_code"]),
                         (1, 1, "B"))
        draw = [leg(1, "A", "B", 81, 81), leg(2, "B", "A", 97, 81)]  # U2014 LIE-KSK shape
        self.assertEqual(derive_rows(draw, "U2014")[0]["winner_club_code"], "B")
        sweep = [leg(1, "A", "B", 80, 70), leg(2, "B", "A", 70, 75)]
        self.assertEqual(derive_rows(sweep, "U2015")[0]["winner_club_code"], "A")

    def test_two_leg_without_both_legs_or_with_level_aggregate_has_no_winner(self):
        level = [leg(1, "A", "B", 80, 70), leg(2, "B", "A", 80, 70)]
        self.assertIsNone(derive_rows(level, "U2015")[0]["winner_club_code"])
        pending = [leg(1, "A", "B", 90, 70), leg(2, "B", "A", 0, 0, played=False)]
        self.assertIsNone(derive_rows(pending, "U2015")[0]["winner_club_code"])

    def test_other_eurocup_ties_are_won_on_game_wins(self):
        best_of_three = [leg(1, "A", "B", 80, 70, "4F"), leg(2, "B", "A", 90, 60, "4F"),
                         leg(3, "A", "B", 71, 70, "4F")]
        row = derive_rows(best_of_three, "U2018")[0]
        self.assertEqual((row["club_a_wins"], row["club_b_wins"], row["winner_club_code"]),
                         (2, 1, "A"))
        sweep = [leg(1, "A", "B", 80, 70, "Final"), leg(2, "B", "A", 60, 61, "Final")]
        self.assertEqual(derive_rows(sweep, "U2024")[0]["winner_club_code"], "A")
        split = [leg(1, "A", "B", 80, 70, "4F"), leg(2, "B", "A", 99, 70, "4F")]
        self.assertIsNone(derive_rows(split, "U2018")[0]["winner_club_code"])

    def test_eurocup_phases_cancelled_games_and_euroleague(self):
        games = [leg(1, "A", "B", 80, 70, "L16"), leg(2, "B", "A", 80, 70, "L16")]
        self.assertEqual(len(derive_rows(games, "U2007")), 1)
        self.assertEqual(derive_rows(games, "U2008"), [])
        cancelled = [game(1, "4F", "A", "B", played=False, status="cancelled")]
        self.assertEqual(derive_rows(cancelled, "U2019"), [])
        split = [leg(1, "A", "B", 80, 70, "PO"), leg(2, "B", "A", 90, 60, "PO")]
        self.assertIsNone(derive_rows(split, "E2025")[0]["winner_club_code"])
        self.assertEqual(derive_rows([leg(1, "A", "B", 80, 70, "8F")], "E2025"), [])

    def test_empty_and_missing_clubs(self):
        self.assertEqual(derive_rows([]), [])
        self.assertEqual(derive_rows([game(1, local=None)]), [])


class StorageTests(unittest.TestCase):
    class Cursor:
        def __init__(self, db):
            self.db = db

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def execute(self, query, params=None):
            self.db.queries.append((query, params))

    class Connection:
        def __init__(self):
            self.queries = []
            self.commits = 0
            self.rollbacks = 0

        def cursor(self):
            return StorageTests.Cursor(self)

        def __enter__(self):
            return self

        def __exit__(self, kind, *_):
            self.commits += not bool(kind)
            self.rollbacks += bool(kind)
            return False

    def test_replace_empty_and_rollback(self):
        db = self.Connection()
        row = derive_rows([game(1, winner="A")])[0]
        with patch("gold_etl.loader.read_series_rows", return_value=[row]), \
                patch("psycopg2.extras.execute_values") as insert:
            self.assertEqual(replace_series_scope(db, "E", "E2025"), 1)
        self.assertEqual(db.commits, 1)
        self.assertEqual(db.queries[-1][1], ("E", "E2025"))
        self.assertEqual(insert.call_args.args[2][0][-1].adapted, row["games"])
        with patch("gold_etl.loader.read_series_rows", return_value=[]), \
                patch("psycopg2.extras.execute_values") as insert:
            self.assertEqual(replace_series_scope(db, "E", "E2025"), 0)
        insert.assert_not_called()
        with patch("gold_etl.loader.read_series_rows", return_value=[row]), \
                patch("psycopg2.extras.execute_values", side_effect=RuntimeError("insert")):
            with self.assertRaises(RuntimeError):
                replace_series_scope(db, "E", "E2025")
        self.assertEqual((db.commits, db.rollbacks), (2, 1))
