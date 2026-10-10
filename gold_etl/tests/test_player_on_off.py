"""Player on/off: sums against the club's other stints, scopes, storage, and totals check."""

import unittest
from decimal import Decimal
from unittest.mock import patch

from gold_etl.player_on_off import derive_rows
from gold_etl.schema import GOLD_TABLES, ON_OFF_ADDITIVE, ROUND_NAMES, columns
from gold_etl.team_pbp import read_silver
from gold_etl.tests.test_team_splits import FakeConnection

D = Decimal


def game(code, phase):
    return {"game_code": code, "phase_code": phase, "played": True}


GAMES = [game(1, "RS"), game(2, "PO")]
FIRST, SECOND = "p1,p2,p3,p4,p5", "p1,p2,p3,p4,p6"


def stint(code, players, start, end, poss, opp, points, against, club="A"):
    return {"game_code": code, "club_code": club, "players": players, "start_seconds": start,
            "end_seconds": end, "possessions_for": poss, "possessions_against": opp,
            "points_for": points, "points_against": against}


STINTS = [stint(1, FIRST, 0, 600, 10, 12, 12, 10), stint(1, SECOND, 600, 2400, 40, 38, 40, 46),
          stint(2, FIRST, 0, 2400, 70, 68, 84, 70)]
PLAYERS = [{"person_key": "p1", "person_name": "ONE, P"}, {"person_key": "p6",
                                                            "person_name": "SIX, P"}]


def pick(rows, scope, person, club="A"):
    return next(r for r in rows if (r["scope"], r["club_code"], r["person_key"])
                == (scope, club, person))


class OnOffTests(unittest.TestCase):
    rows = derive_rows(GAMES, STINTS, PLAYERS)

    def test_on_and_off_sums_and_games(self):
        one, six = pick(self.rows, "all", "p1"), pick(self.rows, "all", "p6")
        self.assertEqual((one["games"], one["on_seconds"], one["off_seconds"]), (2, 4800, 0))
        self.assertEqual((one["on_possessions_for"], one["on_points_against"]), (120, 126))
        self.assertEqual((six["games"], six["on_seconds"], six["off_seconds"]), (1, 1800, 3000))
        self.assertEqual((six["off_possessions_for"], six["off_possessions_against"]), (80, 80))
        self.assertEqual((six["off_points_for"], six["off_points_against"]), (96, 80))
        self.assertEqual(six["player_name"], "SIX, P")
        self.assertIsNone(pick(self.rows, "all", "p5")["player_name"])

    def test_ratings_are_points_per_100_possessions(self):
        six = pick(self.rows, "all", "p6")
        self.assertEqual((six["on_ortg"], six["on_drtg"]), (D(100), D("121.052632")))
        self.assertEqual(six["on_net_rating"], D("-21.052632"))
        self.assertEqual((six["off_ortg"], six["off_drtg"], six["off_net_rating"]),
                         (D(120), D(100), D(20)))
        self.assertEqual((six["ortg_diff"], six["drtg_diff"], six["net_rating_diff"]),
                         (D(-20), D("21.052632"), D("-41.052632")))

    def test_a_player_always_on_court_has_no_off_ratings(self):
        one = pick(self.rows, "all", "p1")
        self.assertEqual((one["off_seconds"], one["off_possessions_for"]), (0, 0))
        for column in ("off_ortg", "off_drtg", "off_net_rating", "ortg_diff", "drtg_diff",
                       "net_rating_diff"):
            self.assertIsNone(one[column], column)

    def test_phase_and_postseason_scopes(self):
        regular, postseason = pick(self.rows, "RS", "p6"), pick(self.rows, "PO", "p1")
        self.assertEqual((regular["games"], regular["on_seconds"], regular["off_seconds"]),
                         (1, 1800, 600))
        self.assertEqual((postseason["games"], postseason["on_points_for"]), (1, 84))
        self.assertEqual(pick(self.rows, "PS", "p1"), dict(postseason, scope="PS"))
        self.assertFalse([r for r in self.rows if r["scope"] == "PO" and r["person_key"] == "p6"])

    def test_each_club_is_separate_and_a_players_clubs_get_their_own_rows(self):
        other = derive_rows(GAMES, STINTS + [stint(1, "p1,q2,q3,q4,q5", 0, 600, 5, 5, 6, 6,
                                                   club="B")], PLAYERS)
        self.assertEqual(pick(other, "all", "p1", "A"), pick(self.rows, "all", "p1"))
        self.assertEqual(pick(other, "all", "p1", "B")["on_seconds"], 600)
        self.assertEqual(pick(other, "all", "p1", "B")["off_seconds"], 0)

    def test_totals_check_invariants_hold(self):
        for scope, club in {(r["scope"], r["club_code"]) for r in self.rows}:
            mine = [r for r in self.rows if (r["scope"], r["club_code"]) == (scope, club)]
            self.assertEqual(sum(r["on_seconds"] for r in mine),
                             5 * (mine[0]["on_seconds"] + mine[0]["off_seconds"]))

    def test_unplayed_games_and_stints_of_unknown_games_are_ignored(self):
        self.assertEqual(derive_rows([dict(GAMES[0], played=False)], STINTS[:2], PLAYERS), [])
        self.assertEqual(derive_rows(GAMES[:1], [stint(9, FIRST, 0, 60, 1, 1, 2, 2)], []), [])

    def test_rows_are_sorted_and_match_the_registered_table(self):
        keys = [(r["scope"], r["club_code"], r["person_key"]) for r in self.rows]
        self.assertEqual(keys, sorted(keys))
        self.assertEqual(set(self.rows[0]) | {"competition_code", "season_code"},
                         set(columns("player_on_off")))
        self.assertIn("player_on_off", ROUND_NAMES)
        self.assertEqual(GOLD_TABLES["player_on_off"].key,
                         ("competition_code", "season_code", "scope", "club_code",
                          "person_key"))
        self.assertEqual(len(ON_OFF_ADDITIVE), 10)


class ReadAndStorageTests(unittest.TestCase):
    def test_read_rows_dispatches_through_the_shared_reader(self):
        from gold_etl import player_on_off
        from gold_etl.loader import read_aggregate_rows

        with patch.object(player_on_off, "read_silver",
                          return_value=[GAMES, STINTS, PLAYERS]) as read:
            rows = read_aggregate_rows(object(), "player_on_off", "E", "E2025")
        self.assertEqual(rows, derive_rows(GAMES, STINTS, PLAYERS))
        self.assertEqual(read.call_args.args[3], ("game_team_lineup_stints",
                                                  "game_player_stats"))

    def test_a_missing_stint_table_names_the_command(self):
        class Cursor:
            description = [("game_code",)]

            def execute(self, query, params=None):
                pass

            def fetchone(self):
                return (None,)

            def fetchall(self):
                return []

        with self.assertRaisesRegex(ValueError, "silver.game_team_lineup_stints is missing; "
                                    "run python postgres_etl/lineups.py"):
            read_silver(Cursor(), "E", "E2025", ("game_team_lineup_stints",))

    def test_replace_is_scoped_and_atomic(self):
        from gold_etl.loader import replace_aggregate_scope

        stored = dict(derive_rows(GAMES, STINTS, PLAYERS)[0],
                      competition_code="E", season_code="E2025")
        db = FakeConnection()
        with patch("gold_etl.loader.read_aggregate_rows", return_value=[stored]), \
                patch("psycopg2.extras.execute_values") as insert:
            self.assertEqual(replace_aggregate_scope(db, "player_on_off", "E", "E2025"), 1)
        self.assertEqual((db.commits, db.rollbacks), (1, 0))
        self.assertTrue(any(query.startswith('DELETE FROM gold."app_player_on_off"')
                            and params == ("E", "E2025") for query, params in db.queries))
        self.assertEqual(insert.call_args.args[2][0][:2], ("E", "E2025"))


class TotalsCheckTests(unittest.TestCase):
    def issues(self, rows):
        from gold_etl.quality import check_on_off_totals

        with patch("gold_etl.quality._dict_rows", return_value=rows):
            return check_on_off_totals(FakeConnection().cursor(), "E", "E2025")

    def test_a_correct_derivation_passes(self):
        self.assertEqual(self.issues(derive_rows(GAMES, STINTS, PLAYERS)), [])

    def test_a_player_whose_on_plus_off_differs_or_missing_seconds_are_reported(self):
        rows = derive_rows(GAMES, STINTS, PLAYERS)
        broken = [dict(r, off_points_for=r["off_points_for"] + 1)
                  if r["person_key"] == "p6" and r["scope"] == "all" else r for r in rows]
        self.assertIn("on plus off differs", self.issues(broken)[0])
        short = [r for r in rows if r["person_key"] != "p5"]
        self.assertTrue(any("five times the team seconds" in i for i in self.issues(short)))


if __name__ == "__main__":
    unittest.main()
