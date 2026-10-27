"""Collapsing re-registrations into one Gold row per person, club and role."""

import unittest
from datetime import datetime
from unittest.mock import patch

from gold_etl.loader import replace_scope
from gold_etl.quality import check_scope
from gold_etl.registrations import collapse
from gold_etl.schema import columns
from gold_etl.tests.test_gold import FakeConnection


def period(key, start, end, active=False, external_id=1, person="P", club="DUB", role="J",
           **changes):
    row = {field: None for field in columns("registrations")}
    row.update(competition_code="E", season_code="E2026", registration_key=key,
               person_key=person, club_code=club, role_code=role, active=active,
               start_at=start and datetime.fromisoformat(start),
               end_at=end and datetime.fromisoformat(end), external_id=external_id)
    row.update(changes)
    return row


def by_group(rows):
    return {(row["person_key"], row["club_code"], row["role_code"]): row for row in rows}


class CollapseTests(unittest.TestCase):
    def test_active_period_after_closed_one(self):
        rows = collapse([
            period("a", "2026-08-12", "2026-09-17", external_id=54775, last_team=None),
            period("b", "2026-09-28", "2027-06-30", active=True, external_id=57034,
                   last_team="DUBAI BASKETBALL", jersey_number="2"),
        ])
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual((row["registration_key"], row["active"], row["last_team"],
                          row["jersey_number"], row["external_id"]),
                         ("b", True, "DUBAI BASKETBALL", "2", 57034))
        self.assertEqual((row["start_at"], row["end_at"]),
                         (datetime(2026, 8, 12), datetime(2027, 6, 30)))

    def test_no_active_period_stays_inactive(self):
        rows = collapse([period("b", "2021-02-24", "2021-06-30"),
                         period("a", "2020-09-30", "2020-10-21")])
        self.assertEqual([(row["registration_key"], row["active"]) for row in rows],
                         [("b", False)])

    def test_three_periods_take_the_latest(self):
        rows = collapse([
            period("c", "2017-01-18", "2017-01-23", sort_order=3),
            period("a", "2016-09-27", "2017-01-11", sort_order=1),
            period("b", "2017-02-08", "2017-06-30", active=True, sort_order=2),
        ])
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["registration_key"], rows[0]["sort_order"]), ("b", 2))
        self.assertEqual((rows[0]["start_at"], rows[0]["end_at"]),
                         (datetime(2016, 9, 27), datetime(2017, 6, 30)))

    def test_missing_dates_are_skipped_and_never_latest(self):
        rows = collapse([period("a", None, None, active=True, external_id=9),
                         period("b", "2020-01-01", None, external_id=1)])
        self.assertEqual((rows[0]["registration_key"], rows[0]["active"]), ("b", True))
        self.assertEqual((rows[0]["start_at"], rows[0]["end_at"]), (datetime(2020, 1, 1), None))
        tie = collapse([period("a", "2020-01-01", None, external_id=2),
                        period("b", "2020-01-01", "2020-05-01", external_id=1)])
        self.assertEqual(tie[0]["registration_key"], "b")
        same = collapse([period("a", "2020-01-01", "2020-05-01", external_id=2),
                         period("b", "2020-01-01", "2020-05-01", external_id=1)])
        self.assertEqual(same[0]["registration_key"], "a")

    def test_single_period_is_unchanged(self):
        row = period("a", None, None, active=None)
        self.assertEqual(collapse([row]), [row])

    def test_transfers_roles_and_seasons_stay_separate(self):
        rows = collapse([
            period("a", "2024-09-01", "2024-12-01", club="MAD"),
            period("b", "2025-01-01", "2025-06-30", club="BAR", active=True),
            period("c", "2024-09-01", "2025-06-30", club="MAD", role="A"),
            period("d", "2024-09-01", "2025-06-30", club="MAD", season_code="E2025"),
        ])
        self.assertEqual(sorted(row["registration_key"] for row in rows), ["a", "b", "c", "d"])
        self.assertFalse(by_group(rows)[("P", "MAD", "J")]["active"])


class StorageTests(unittest.TestCase):
    def test_replace_writes_collapsed_rows_in_one_transaction(self):
        db = FakeConnection()
        writes = []
        rows = collapse([period("a", "2026-08-12", "2026-09-17"),
                         period("b", "2026-09-28", "2027-06-30", active=True)])
        with patch("gold_etl.loader.read_registration_rows", return_value=rows), \
                patch("psycopg2.extras.execute_values",
                      side_effect=lambda _, sql, values, page_size: writes.append((sql, values))):
            self.assertEqual(replace_scope(db, "registrations", "E", "E2026"), 1)
        self.assertEqual((db.commits, db.rollbacks), (1, 0))
        self.assertTrue(any(query.startswith('DELETE FROM gold."app_registrations"')
                            and params == ("E", "E2026") for query, params in db.statements))
        self.assertFalse(any(query.startswith("INSERT INTO") for query, _ in db.statements))
        self.assertIn('INSERT INTO gold."app_registrations"', writes[0][0])
        self.assertEqual(len(writes[0][1]), 1)

    def test_insert_failure_rolls_back(self):
        db = FakeConnection()
        with patch("gold_etl.loader.read_registration_rows",
                   return_value=[period("a", None, None)]), \
                patch("psycopg2.extras.execute_values", side_effect=RuntimeError("failed")):
            with self.assertRaisesRegex(RuntimeError, "failed"):
                replace_scope(db, "registrations", "E", "E2026")
        self.assertEqual((db.commits, db.rollbacks), (0, 1))

    def test_quality_compares_gold_with_collapsed_silver(self):
        silver = [period("a", "2026-08-12", "2026-09-17"),
                  period("b", "2026-09-28", "2027-06-30", active=True)]
        expected = collapse(silver)
        db = FakeConnection()
        with db.cursor() as cursor:
            with patch("gold_etl.quality.read_registration_rows", return_value=expected), \
                    patch("gold_etl.quality._dict_rows", return_value=expected):
                self.assertEqual(check_scope(cursor, "registrations", "E", "E2026"), [])
            with patch("gold_etl.quality.read_registration_rows", return_value=expected), \
                    patch("gold_etl.quality._dict_rows", return_value=silver):
                self.assertIn("keys differ",
                              check_scope(cursor, "registrations", "E", "E2026")[0])
            changed = [{**expected[0], "active": False}]
            with patch("gold_etl.quality.read_registration_rows", return_value=expected), \
                    patch("gold_etl.quality._dict_rows", return_value=changed):
                self.assertIn("values differ",
                              check_scope(cursor, "registrations", "E", "E2026")[0])


if __name__ == "__main__":
    unittest.main()
