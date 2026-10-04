"""Calculated perGame rows and the qualification checks."""

import unittest
from decimal import Decimal

from gold_etl.per_game_rows import calculated_rows, derive_per_game
from gold_etl.quality import player_stats_issues
from gold_etl.schema import columns

TRADITIONAL = "season_player_stats_traditional"


def accumulated(name=TRADITIONAL, phase="RS", person="A", ordinal=0, games=4, **values):
    row = {column: None for column in columns(name)}
    row.update(competition_code="E", season_code="E2025", phase_code=phase,
               mode="accumulated", entry_ordinal=ordinal, person_key=person,
               club_code="MAD", player_name=person, games_played=Decimal(games),
               player_ranking=3, is_calculated=False, min_games=0, qualified=False)
    row.update(values)
    return row


class DeriveTests(unittest.TestCase):
    def test_counting_stats_become_half_even_averages(self):
        row = derive_per_game(TRADITIONAL, accumulated(points=Decimal(9), assists=Decimal(10),
                                                       pir=None, minutes_played=Decimal(150)))
        self.assertEqual(row["points"], Decimal("2.2"))
        self.assertEqual(row["assists"], Decimal("2.5"))
        self.assertIsNone(row["pir"])
        self.assertEqual(row["minutes_played"], Decimal("37.5"))
        self.assertEqual(row["mode"], "perGame")

    def test_percentages_games_and_identity_are_copied(self):
        source = accumulated(two_pointers_percentage=Decimal("51.2"),
                             games_started=Decimal(3), player_image_url="a.png",
                             club_code="BAR", player_age=Decimal(27))
        row = derive_per_game(TRADITIONAL, source)
        for column in ("two_pointers_percentage", "games_started", "games_played",
                       "player_image_url", "club_code", "player_age", "person_key"):
            self.assertEqual(row[column], source[column], column)

    def test_ranking_is_null_and_row_is_flagged_calculated(self):
        row = derive_per_game(TRADITIONAL, accumulated())
        self.assertIsNone(row["player_ranking"])
        self.assertIs(row["is_calculated"], True)

    def test_other_tables_copy_every_metric(self):
        name = "season_player_stats_advanced"
        source = accumulated(name, minutes_played=Decimal("20.5"), possessions=Decimal("14.8"),
                             true_shooting_percentage=Decimal("55.5"))
        row = derive_per_game(name, source)
        for column in ("minutes_played", "possessions", "true_shooting_percentage"):
            self.assertEqual(row[column], source[column], column)
        self.assertEqual(source["mode"], "accumulated")


class CalculatedRowsTests(unittest.TestCase):
    def test_ordinals_continue_after_the_feed_per_phase(self):
        missing = [accumulated(person="A", ordinal=5), accumulated(person="B", ordinal=7),
                   accumulated(phase="PO", person="A", ordinal=1)]
        rows = calculated_rows(TRADITIONAL, missing, {"RS": 205})
        self.assertEqual([(row["phase_code"], row["person_key"], row["entry_ordinal"])
                          for row in rows],
                         [("RS", "A", 206), ("RS", "B", 207), ("PO", "A", 0)])

    def test_nothing_missing_adds_nothing(self):
        self.assertEqual(calculated_rows(TRADITIONAL, [], {"RS": 3}), [])


def pair(person="A", games=25, threshold=20, qualified=True, calculated=False, phase="RS"):
    feed = accumulated(person=person, phase=phase, games=games, points=Decimal(50),
                       min_games=threshold, qualified=games >= threshold)
    per_game = derive_per_game(TRADITIONAL, feed)
    per_game.update(entry_ordinal=0, is_calculated=calculated, min_games=threshold,
                    qualified=qualified)
    return [feed, per_game]


class IssueTests(unittest.TestCase):
    rounds = {"RS": 38, "all": 38}

    def issues(self, rows, rounds=None):
        return player_stats_issues(TRADITIONAL, "E2025", rows, rounds or self.rounds)

    def test_consistent_rows_have_no_issues(self):
        rows = pair() + pair("B", games=12, qualified=False, calculated=True)
        self.assertEqual(self.issues(rows), [])

    def test_qualified_must_follow_games_and_min_games(self):
        issues = self.issues(pair(games=12, qualified=True))
        self.assertTrue(any("qualified does not match" in issue for issue in issues))

    def test_min_games_must_match_the_rule(self):
        issues = self.issues(pair(threshold=18))
        self.assertTrue(any("min_games [18], expected 20" in issue for issue in issues))

    def test_every_accumulated_row_needs_a_per_game_row(self):
        issues = self.issues(pair()[:1])
        self.assertTrue(any("has no perGame row" in issue for issue in issues))

    def test_calculated_row_must_match_its_accumulated_row(self):
        rows = pair("B", games=12, qualified=False, calculated=True)
        rows[1]["points"] = Decimal("9.9")
        issues = self.issues(rows)
        self.assertTrue(any("differs from its accumulated row in points" in issue
                            for issue in issues))

    def test_feed_rows_are_not_recomputed(self):
        rows = pair()
        rows[1]["points"] = Decimal("9.9")
        self.assertEqual(self.issues(rows), [])


if __name__ == "__main__":
    unittest.main()
