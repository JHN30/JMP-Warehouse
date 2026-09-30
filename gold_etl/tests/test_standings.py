"""Historical page-shaped standings contract over typed Silver feeds."""

import unittest
from datetime import datetime, timezone

from gold_etl.schema import (STANDINGS_FEEDS, STANDINGS_TABLE, columns,
                             create_table_sql, feed_fields)
from gold_etl.quality import standings_feed_lag
from gold_etl.standings import derive_rows, iso_milliseconds


def item(club="MAD", **values):
    return {"competition_code": "E", "season_code": "E2025",
            "phase_code": "RS", "round_number": 3, "club_code": club, **values}


class StandingsTests(unittest.TestCase):
    def test_schema_uses_historical_page_key_and_typed_feed_columns(self):
        self.assertEqual(STANDINGS_TABLE.key,
                         ("competition_code", "season_code", "phase_code",
                          "round_number", "club_code"))
        names = columns("app_standings")
        self.assertEqual(len(names), len(set(names)))
        self.assertIn("basic_win_percentage", names)
        self.assertIn("streaks_longest_lose_streak_current_season", names)
        self.assertIn("ahead_behind_quarter1_ahead", names)
        self.assertIn("margins_point_difference_1_to_5", names)
        self.assertIn('"form" JSONB NOT NULL', create_table_sql("app_standings"))
        self.assertIn('"streak_history" JSONB NOT NULL',
                      create_table_sql("app_standings"))
        for source, prefix in STANDINGS_FEEDS:
            for field in feed_fields(source):
                name = field.name.replace("longest_loss", "longest_lose")
                self.assertIn(f"{prefix}_{name}", names)

    def test_merge_full_feeds_and_ordered_lists(self):
        feeds = {
            "standings_basic": [item(club_name="Madrid", club_tv_code="RMB",
                                      group_name="A", position=1, win_percentage=75)],
            "standings_calendar": [item(position=2, games_played=3)],
            "standings_streaks": [item(longest_loss_streak_current_season=2)],
            "standings_ahead_behind": [item(quarter1_ahead="4-1")],
            "standings_margins": [item(point_difference_1_to_5="3-0")],
            "standings_basic_form": [item(result_ordinal=1, result="L"),
                                      item(result_ordinal=0, result="W")],
            "standings_calendar_streaks": [
                item(streak_ordinal=1, start_at=None, end_at=None,
                     win_loss_record="0-1"),
                item(streak_ordinal=0, start_at=datetime(2025, 9, 1),
                     end_at=datetime(2025, 9, 30, tzinfo=timezone.utc),
                     win_loss_record="1-0")],
        }
        rows = derive_rows(feeds, [{"competition_code": "E", "season_code": "E2025",
                                    "club_code": "MAD", "crest_url": "mad.png"}])
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual((row["club_name"], row["crest_url"], row["basic_position"],
                          row["calendar_position"]), ("Madrid", "mad.png", 1, 2))
        self.assertEqual(row["streaks_longest_lose_streak_current_season"], 2)
        self.assertEqual(row["ahead_behind_quarter1_ahead"], "4-1")
        self.assertEqual(row["margins_point_difference_1_to_5"], "3-0")
        self.assertEqual(row["form"], [{"resultOrdinal": 0, "result": "W"},
                                        {"resultOrdinal": 1, "result": "L"}])
        self.assertEqual(row["streak_history"], [
            {"streakOrdinal": 0, "startAt": "2025-09-01T00:00:00.000Z",
             "endAt": "2025-09-30T00:00:00.000Z", "winLossRecord": "1-0"},
            {"streakOrdinal": 1, "startAt": None, "endAt": None,
             "winLossRecord": "0-1"},
        ])

    def test_missing_feeds_club_and_children(self):
        rows = derive_rows({"standings_basic": [item(position=1)]}, [])
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertIsNone(row["crest_url"])
        for source, prefix in STANDINGS_FEEDS[1:]:
            for field in feed_fields(source):
                self.assertIsNone(row[f'{prefix}_{field.name.replace("longest_loss", "longest_lose")}'])
        self.assertEqual((row["form"], row["streak_history"]), ([], []))
        self.assertEqual(derive_rows({}, []), [])

    def test_duplicate_parent_and_child_keys_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate standings_basic key"):
            derive_rows({"standings_basic": [item(), item()]}, [])
        with self.assertRaisesRegex(ValueError, "Duplicate standings_basic_form key"):
            derive_rows({"standings_basic": [item()],
                         "standings_basic_form": [item(result_ordinal=0),
                                                  item(result_ordinal=0)]}, [])

    def test_iso_dates_convert_aware_offsets_to_utc(self):
        self.assertEqual(iso_milliseconds("2025-09-01T02:30:00+02:00"),
                         "2025-09-01T00:30:00.000Z")
        self.assertIsNone(iso_milliseconds(None))

    def test_lagging_feeds_of_a_round_are_named_against_the_most_advanced(self):
        rows = derive_rows({
            "standings_basic": [item("ULK", games_played=2, games_won=2),
                                item("DUB", games_played=2, games_won=2)],
            "standings_streaks": [item("ULK", games_played=1, games_won=1),
                                  item("DUB", games_played=2, games_won=2)],
            "standings_margins": [item("ULK", games_played=1, games_won=1)],
        }, [])
        warnings = standings_feed_lag(rows, "E2025")
        self.assertEqual(len(warnings), 4)
        self.assertIn("RS round 3: margins_games_played is behind the other feeds "
                      "for 1 club(s) (e.g. ULK: 1 vs 2)", warnings[0])
        self.assertIn("streaks_games_won", warnings[3])
        self.assertFalse(any("basic_" in warning for warning in warnings))

    def test_consistent_or_absent_feeds_give_no_lag_warning(self):
        rows = derive_rows({
            "standings_basic": [item("ULK", games_played=2, games_won=2)],
            "standings_calendar": [item("ULK", games_played=2, games_won=2)],
        }, [])
        self.assertEqual(standings_feed_lag(rows, "E2025"), [])
        self.assertEqual(standings_feed_lag(derive_rows({"standings_basic": [item()]}, []),
                                            "E2025"), [])


if __name__ == "__main__":
    unittest.main()
