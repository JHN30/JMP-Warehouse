"""Global record ranking and atomic replacement."""

import sqlite3
import unittest
from unittest.mock import patch

from gold_etl.loader import replace_records_scope
from gold_etl.records import METRICS, select_sql
from gold_etl.schema import columns


class RecordQueryTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.execute("ATTACH DATABASE ':memory:' AS silver")
        self.db.executescript("""
            CREATE TABLE silver.season_player_stats_traditional
                (competition_code, season_code, phase_code, mode, entry_ordinal,
                 person_key, player_name, club_code, club_name, points,
                 total_rebounds, assists, pir);
            CREATE TABLE silver.games
                (competition_code, season_code, game_code, played, scheduled_at,
                 local_club_code, road_club_code, local_club_name, road_club_name);
            CREATE TABLE silver.game_player_stats
                (competition_code, season_code, game_code, side, person_key,
                 person_name, club_code, club_name, points, pir,
                 total_rebounds, assists);
            CREATE TABLE silver.game_team_stats
                (competition_code, season_code, game_code, side, stats_kind,
                 points, pir, total_rebounds, assists);
        """)

    def tearDown(self):
        self.db.close()

    def ranked(self, name):
        query, count = select_sql(name)
        cursor = self.db.execute(query.replace("%s", "?"), ("E",) * count)
        return [dict(zip(columns(name), row)) for row in cursor.fetchall()]

    def test_player_season_filter_mapping_and_ties(self):
        rows = [("E", "E2026", "all", "accumulated", 1, "Z", "Zed", "Z", "Z", 30, 2, 3, 4),
                ("E", "E2025", "all", "accumulated", 1, "B", "Bee", "B", "B", 30, 2, 3, 4),
                ("E", "E2025", "all", "accumulated", 2, "A", "Aye", "A", "A", 30, 2, 3, 4),
                ("E", "E2025", "PS", "accumulated", 3, "X", "X", "X", "X", 99, 9, 9, 9),
                ("E", "E2025", "all", "perGame", 4, "Y", "Y", "Y", "Y", 88, 8, 8, 8),
                ("U", "U2025", "all", "accumulated", 1, "U", "U", "U", "U", 77, 7, 7, 7)]
        self.db.executemany("INSERT INTO silver.season_player_stats_traditional VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        ranked = [row for row in self.ranked("app_records_player_seasons")
                  if row["metric"] == "points_scored"]
        self.assertEqual([(row["rank_ordinal"], row["person_key"], row["value"])
                          for row in ranked], [(1, "A", 30), (2, "B", 30), (3, "Z", 30)])

    def test_single_game_excludes_unplayed_and_ranks_ties(self):
        self.db.executemany("INSERT INTO silver.games VALUES (?,?,?,?,?,?,?,?,?)", [
            ("E", "E2025", 1, 1, "date", "A", "B", "A", "B"),
            ("E", "E2025", 2, 0, "date", "A", "B", "A", "B"),
            ("E", "E2026", 1, 1, "date", "A", "B", "A", "B")])
        self.db.executemany("INSERT INTO silver.game_player_stats VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", [
            ("E", "E2025", 1, "local", "B", "B", "A", "A", 20, 3, 4, 5),
            ("E", "E2025", 1, "road", "A", "A", "B", "B", 20, 3, 4, 5),
            ("E", "E2025", 2, "local", "X", "X", "A", "A", 99, 9, 9, 9),
            ("E", "E2026", 1, "local", "C", "C", "A", "A", None, 3, 4, 5)])
        ranked = [row for row in self.ranked("app_records_single_games")
                  if row["metric"] == "points"]
        self.assertEqual([(row["rank_ordinal"], row["person_key"])
                          for row in ranked], [(1, "A"), (2, "B")])
        self.assertEqual({row["metric"] for row in self.ranked("app_records_single_games")},
                         {metric for metric, _ in METRICS["app_records_single_games"]})

    def test_team_totals_use_played_total_rows_and_club_identity(self):
        self.db.executemany("INSERT INTO silver.games VALUES (?,?,?,?,?,?,?,?,?)", [
            ("E", "E2025", 1, 1, "date", "A", "B", "A", "B"),
            ("E", "E2025", 2, 1, "date", "B", "A", "B", "A"),
            ("E", "E2025", 3, 0, "date", "A", "B", "A", "B")])
        self.db.executemany("INSERT INTO silver.game_team_stats VALUES (?,?,?,?,?,?,?,?,?)", [
            ("E", "E2025", 1, "local", "total", 90, 10, 20, 12),
            ("E", "E2025", 2, "road", "total", 95, 11, 21, 13),
            ("E", "E2025", 1, "road", "total", 80, 9, 19, 11),
            ("E", "E2025", 3, "local", "total", 200, 20, 20, 20),
            ("E", "E2025", 2, "local", "team", 300, 30, 30, 30)])
        ranked = [row for row in self.ranked("app_records_team_seasons")
                  if row["metric"] == "points"]
        self.assertEqual([(row["club_code"], row["value"]) for row in ranked],
                         [("A", 185), ("B", 80)])

    def test_top_fifty_and_empty_metric(self):
        rows = [("E", "E2025", "all", "accumulated", n, str(n), "P", "A", "A", n,
                 None, None, None) for n in range(1, 56)]
        self.db.executemany("INSERT INTO silver.season_player_stats_traditional VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        ranked = self.ranked("app_records_player_seasons")
        self.assertEqual(len(ranked), 50)
        self.assertEqual([row["rank_ordinal"] for row in ranked], list(range(1, 51)))
        self.assertEqual(ranked[0]["value"], 55)


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
            self.rollbacks += bool(kind)
            self.commits += not bool(kind)
            return False

    def test_full_competition_replace_and_failure(self):
        db = self.Connection()
        name = "app_records_team_seasons"
        row = dict(zip(columns(name), ("E", "points", 1, "E2025", "A", "A", 90)))
        with patch("gold_etl.loader.read_record_rows", return_value=[row]), \
                patch("psycopg2.extras.execute_values") as insert:
            self.assertEqual(replace_records_scope(db, name, "E"), 1)
        self.assertEqual(db.commits, 1)
        self.assertEqual(db.queries[-1][1], ("E",))
        self.assertIn("DELETE FROM gold", db.queries[-1][0])
        insert.assert_called_once()
        with patch("gold_etl.loader.read_record_rows", return_value=[]), \
                patch("psycopg2.extras.execute_values") as insert:
            self.assertEqual(replace_records_scope(db, name, "E"), 0)
        insert.assert_not_called()
        with patch("gold_etl.loader.read_record_rows", return_value=[row]), \
                patch("psycopg2.extras.execute_values", side_effect=RuntimeError("insert")):
            with self.assertRaises(RuntimeError):
                replace_records_scope(db, name, "E")
        self.assertEqual((db.commits, db.rollbacks), (2, 1))
