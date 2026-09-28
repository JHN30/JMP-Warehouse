"""Atomic local standings replacement and full read-only comparison."""

import unittest
from unittest.mock import patch

from gold_etl.loader import replace_standings_scope
from gold_etl.quality import check_standings_scope
from gold_etl.schema import columns


class Cursor:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, query, params=None):
        self.connection.queries.append((query, params))

    def fetchone(self):
        return ("gold.app_standings" if self.connection.exists else None,)


class Connection:
    def __init__(self):
        self.queries = []
        self.commits = 0
        self.rollbacks = 0
        self.exists = True

    def __enter__(self):
        return self

    def __exit__(self, kind, *_):
        if kind:
            self.rollbacks += 1
        else:
            self.commits += 1
        return False

    def cursor(self):
        return Cursor(self)


def page(club="MAD", position=1):
    row = {name: None for name in columns("app_standings")}
    row.update(competition_code="E", season_code="E2025", phase_code="RS",
               round_number=3, club_code=club, basic_position=position,
               form=[], streak_history=[])
    return row


class StandingsStorageTests(unittest.TestCase):
    def test_replace_one_scope_and_rerun_with_json_lists(self):
        db = Connection()
        row = page()
        row["form"] = [{"resultOrdinal": 0, "result": "W"}]
        writes = []

        def capture(_, query, values, page_size):
            writes.append((query, values, page_size))

        with patch("gold_etl.loader.read_standings_rows", return_value=[row]), \
                patch("psycopg2.extras.execute_values", side_effect=capture):
            self.assertEqual(replace_standings_scope(db, "E", "E2025"), 1)
            self.assertEqual(replace_standings_scope(db, "E", "E2025"), 1)
        self.assertEqual(db.commits, 2)
        self.assertEqual(len(writes), 2)
        self.assertIn('INSERT INTO gold."app_standings"', writes[0][0])
        self.assertEqual(writes[0][1][0][columns("app_standings").index("form")].adapted,
                         row["form"])
        deletes = [(q, p) for q, p in db.queries if q.startswith("DELETE")]
        self.assertEqual(len(deletes), 2)
        self.assertTrue(all("gold." in q and p == ("E", "E2025")
                            for q, p in deletes))
        self.assertFalse(any(q.startswith(("DELETE FROM silver", "INSERT INTO silver"))
                             or "neon" in q.lower() for q, _ in db.queries))

    def test_empty_source_clears_stale_gold_scope(self):
        db = Connection()
        with patch("gold_etl.loader.read_standings_rows", return_value=[]), \
                patch("psycopg2.extras.execute_values") as insert:
            self.assertEqual(replace_standings_scope(db, "E", "E2025"), 0)
        insert.assert_not_called()
        self.assertEqual((db.commits, db.rollbacks), (1, 0))
        self.assertEqual(sum(q.startswith("DELETE") for q, _ in db.queries), 1)

    def test_insert_failure_rolls_back_prior_rows(self):
        db = Connection()
        with patch("gold_etl.loader.read_standings_rows", return_value=[page()]), \
                patch("psycopg2.extras.execute_values", side_effect=RuntimeError("failed")):
            with self.assertRaisesRegex(RuntimeError, "failed"):
                replace_standings_scope(db, "E", "E2025")
        self.assertEqual((db.commits, db.rollbacks), (0, 1))

    def test_quality_missing_key_and_value_mismatch(self):
        db = Connection()
        with db.cursor() as cursor:
            db.exists = False
            self.assertEqual(check_standings_scope(cursor, "E", "E2025"),
                             ["gold.app_standings is missing"])
            db.exists = True
            with patch("gold_etl.quality.read_standings_rows", return_value=[page()]), \
                    patch("gold_etl.quality._dict_rows", return_value=[]):
                self.assertIn("keys differ", check_standings_scope(cursor, "E", "E2025")[0])
            with patch("gold_etl.quality.read_standings_rows", return_value=[page()]), \
                    patch("gold_etl.quality._dict_rows", return_value=[page(position=2)]):
                self.assertIn("feed fields or lists differ",
                              check_standings_scope(cursor, "E", "E2025")[0])
            with patch("gold_etl.quality.read_standings_rows", return_value=[page()]), \
                    patch("gold_etl.quality._dict_rows", return_value=[page()]):
                self.assertEqual(check_standings_scope(cursor, "E", "E2025"), [])


if __name__ == "__main__":
    unittest.main()
