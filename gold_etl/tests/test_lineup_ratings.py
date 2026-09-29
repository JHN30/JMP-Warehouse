"""Lineup ratings: 2, 3 and 5-man groups summed over stints, scopes, storage, invariants."""

import unittest
from decimal import Decimal
from unittest.mock import patch

from gold_etl.lineup_ratings import derive_rows
from gold_etl.schema import GOLD_TABLES, ROUND_NAMES, columns
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
PLAYERS = [{"person_key": "p1", "person_name": "ONE, P"},
           {"person_key": "p2", "person_name": "TWO, P"}]


def pick(rows, scope, size, lineup, club="A"):
    return next(r for r in rows if (r["scope"], r["club_code"], r["lineup_size"], r["lineup"])
                == (scope, club, size, lineup))


class LineupTests(unittest.TestCase):
    rows = derive_rows(GAMES, STINTS, PLAYERS)

    def test_group_counts_per_size(self):
        counts = {size: sum(1 for r in self.rows if r["scope"] == "all"
                            and r["lineup_size"] == size) for size in (2, 3, 5)}
        self.assertEqual(counts, {2: 14, 3: 16, 5: 2})

    def test_five_man_rows_are_the_stints_summed_per_lineup(self):
        five = pick(self.rows, "all", 5, FIRST)
        self.assertEqual((five["games"], five["seconds"]), (2, 3000))
        self.assertEqual((five["possessions_for"], five["possessions_against"]), (80, 80))
        self.assertEqual((five["points_for"], five["points_against"]), (96, 80))
        self.assertEqual((five["ortg"], five["drtg"], five["net_rating"]),
                         (D(120), D(100), D(20)))

    def test_pairs_and_triples_sum_every_stint_that_holds_the_group(self):
        shared = pick(self.rows, "all", 2, "p1,p2")
        self.assertEqual((shared["games"], shared["seconds"], shared["points_for"]), (2, 4800, 136))
        self.assertEqual((shared["possessions_for"], shared["possessions_against"]), (120, 118))
        only_first = pick(self.rows, "all", 3, "p3,p4,p5")
        self.assertEqual((only_first["seconds"], only_first["games"]), (3000, 2))
        only_second = pick(self.rows, "all", 2, "p1,p6")
        self.assertEqual((only_second["seconds"], only_second["games"]), (1800, 1))

    def test_names_follow_the_lineup_order_and_fall_back_to_the_key(self):
        self.assertEqual(pick(self.rows, "all", 2, "p1,p2")["lineup_names"], "ONE, P; TWO, P")
        self.assertEqual(pick(self.rows, "all", 2, "p3,p4")["lineup_names"], "p3; p4")

    def test_a_group_without_possessions_has_null_ratings(self):
        rows = derive_rows(GAMES, [stint(1, FIRST, 0, 30, 0, 0, 0, 0)], PLAYERS)
        five = pick(rows, "all", 5, FIRST)
        self.assertEqual((five["ortg"], five["drtg"], five["net_rating"]), (None, None, None))

    def test_phase_and_postseason_scopes(self):
        regular, postseason = pick(self.rows, "RS", 5, FIRST), pick(self.rows, "PO", 5, FIRST)
        self.assertEqual((regular["games"], regular["seconds"]), (1, 600))
        self.assertEqual((postseason["games"], postseason["seconds"]), (1, 2400))
        self.assertEqual(pick(self.rows, "PS", 5, FIRST), dict(postseason, scope="PS"))
        self.assertFalse([r for r in self.rows if r["scope"] == "PO" and "p6" in r["lineup"]])

    def test_each_club_is_separate(self):
        other = derive_rows(GAMES, STINTS + [stint(1, "p1,q2,q3,q4,q5", 0, 600, 5, 5, 6, 6,
                                                   club="B")], PLAYERS)
        self.assertEqual(pick(other, "all", 2, "p1,p2"), pick(self.rows, "all", 2, "p1,p2"))
        self.assertEqual(pick(other, "all", 2, "p1,q2", "B")["seconds"], 600)

    def test_unplayed_games_and_stints_of_unknown_games_are_ignored(self):
        self.assertEqual(derive_rows([dict(GAMES[0], played=False)], STINTS[:2], PLAYERS), [])
        self.assertEqual(derive_rows(GAMES[:1], [stint(9, FIRST, 0, 60, 1, 1, 2, 2)], []), [])

    def test_rows_are_sorted_and_match_the_registered_table(self):
        keys = [(r["scope"], r["club_code"], r["lineup_size"], r["lineup"]) for r in self.rows]
        self.assertEqual(keys, sorted(keys))
        self.assertEqual(set(self.rows[0]) | {"competition_code", "season_code"},
                         set(columns("lineup_ratings")))
        self.assertIn("lineup_ratings", ROUND_NAMES)
        self.assertEqual(GOLD_TABLES["lineup_ratings"].key,
                         ("competition_code", "season_code", "scope", "club_code",
                          "lineup_size", "lineup"))


class ReadAndStorageTests(unittest.TestCase):
    def test_read_rows_dispatches_through_the_shared_reader(self):
        from gold_etl import lineup_ratings
        from gold_etl.loader import read_aggregate_rows

        with patch.object(lineup_ratings, "read_silver",
                          return_value=[GAMES, STINTS, PLAYERS]) as read:
            rows = read_aggregate_rows(object(), "lineup_ratings", "E", "E2025")
        self.assertEqual(rows, derive_rows(GAMES, STINTS, PLAYERS))
        self.assertEqual(read.call_args.args[3], ("game_team_lineup_stints",
                                                  "game_player_stats"))

    def test_replace_is_scoped_and_atomic(self):
        from gold_etl.loader import replace_aggregate_scope

        stored = dict(derive_rows(GAMES, STINTS, PLAYERS)[0],
                      competition_code="E", season_code="E2025")
        db = FakeConnection()
        with patch("gold_etl.loader.read_aggregate_rows", return_value=[stored]), \
                patch("psycopg2.extras.execute_values") as insert:
            self.assertEqual(replace_aggregate_scope(db, "lineup_ratings", "E", "E2025"), 1)
        self.assertEqual((db.commits, db.rollbacks), (1, 0))
        self.assertTrue(any(query.startswith('DELETE FROM gold."lineup_ratings"')
                            and params == ("E", "E2025") for query, params in db.queries))
        self.assertEqual(insert.call_args.args[2][0][:2], ("E", "E2025"))


class TotalsCheckTests(unittest.TestCase):
    def issues(self, rows):
        from gold_etl.quality import check_lineup_totals

        with patch("gold_etl.quality._dict_rows", return_value=rows):
            return check_lineup_totals(FakeConnection().cursor(), "E", "E2025")

    def test_a_correct_derivation_passes(self):
        self.assertEqual(self.issues(derive_rows(GAMES, STINTS, PLAYERS)), [])

    def test_a_wrong_group_total_or_a_missing_size_is_reported(self):
        rows = derive_rows(GAMES, STINTS, PLAYERS)
        broken = [dict(r, points_for=r["points_for"] + 1)
                  if (r["scope"], r["lineup_size"], r["lineup"]) == ("all", 2, "p1,p2") else r
                  for r in rows]
        self.assertIn("points_for of the 2-man rows is not ten times", self.issues(broken)[0])
        no_triples = [r for r in rows if r["lineup_size"] != 3]
        self.assertTrue(any("3-man rows" in issue for issue in self.issues(no_triples)))


if __name__ == "__main__":
    unittest.main()
