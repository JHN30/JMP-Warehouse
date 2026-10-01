"""Per-game advanced rows: projection, single-game PER, null handling, storage."""

import unittest
from decimal import Decimal
from unittest.mock import patch

from gold_etl.game_advanced import player_rows, team_rows
from gold_etl.player_ratings import derive_rows as round_rating_rows
from gold_etl.schema import GAME_ADVANCED_NAMES, GOLD_TABLES, columns
from gold_etl.tests.test_player_ratings import one_game
from gold_etl.tests.test_player_rounds import (LOCAL, ROAD, FakeConnection, box, game, player)


def advanced_rows(players):
    """Silver `game_player_advanced` stand-ins with the fields the projection keeps."""
    return [{"game_code": p["game_code"], "side": p["side"], "person_key": p["person_key"],
             "club_code": p["club_code"], "seconds_played": p["seconds_played"],
             "game_score": Decimal(1),
             "usage_pct": Decimal("0.25") if p["seconds_played"] else None,
             "assist_pct": None, "orb_pct": None, "drb_pct": None, "trb_pct": None,
             "steal_pct": None, "block_pct": None, "tov_pct": None, "efg_pct": None,
             "true_shooting_pct": None} for p in players]


def derive(games, boxes, players):
    stats = [row for rows, _ in boxes for row in rows]
    advanced = [row for _, rows in boxes for row in rows]
    return player_rows(games, stats, advanced, players, advanced_rows(players))


def pick(rows, key, code=1):
    return next(row for row in rows if (row["game_code"], row["person_key"]) == (code, key))


class PlayerTests(unittest.TestCase):
    def test_columns_match_the_registered_table(self):
        rows = derive(*one_game())
        self.assertEqual(set(rows[0]) | {"competition_code", "season_code"},
                         set(columns("game_player_advanced")))

    def test_first_game_equals_the_round_one_rating(self):
        games, boxes, players = one_game()
        stats = [row for rows, _ in boxes for row in rows]
        advanced = [row for _, rows in boxes for row in rows]
        rating = next(r for r in round_rating_rows(games, stats, advanced, [], players)
                      if (r["scope"], r["round_number"], r["person_key"]) == ("RS", 1, "P1"))
        row = pick(derive(games, boxes, players), "P1")
        self.assertEqual((row["game_uper"], row["game_aper"], row["game_per"]),
                         (rating["uper"], rating["aper"], rating["per"]))

    def test_mean_is_15_for_each_game_round_and_phases_do_not_mix(self):
        games, boxes, players = one_game()
        games += [game(2, 2, local="BAR", road="MAD"), game(3, 41, phase="PO")]
        boxes += [box(2, local=ROAD, road=LOCAL, possessions="80", minutes=45),
                  box(3, possessions="75")]
        players += [player(2, "P1", side="road", club="MAD", **dict(LOCAL, seconds_played=1500)),
                    player(2, "R1", side="local", club="BAR", **dict(ROAD, seconds_played=13500)),
                    player(3, "P1", **dict(LOCAL, seconds_played=1200)),
                    player(3, "R1", side="road", club="BAR", **dict(ROAD, seconds_played=12000))]
        rows = derive(games, boxes, players)
        for code in (1, 2, 3):
            group = [r for r in rows if r["game_code"] == code and r["game_per"] is not None]
            seconds = sum(float(r["seconds_played"]) for r in group)
            mean = sum(float(r["game_per"]) * float(r["seconds_played"]) for r in group) / seconds
            self.assertAlmostEqual(mean, 15, places=4)

    def test_zero_minutes_and_missing_inputs_are_null_not_zero(self):
        games, boxes, players = one_game()
        players.append(player(1, "DNP", seconds_played=0))
        players[1]["assists"] = None
        rows = derive(games, boxes, players)
        dnp = pick(rows, "DNP")
        self.assertEqual((dnp["game_uper"], dnp["game_aper"], dnp["game_per"]), (None,) * 3)
        self.assertIsNone(dnp["usage_pct"])
        self.assertIsNone(pick(rows, "P2")["game_per"])
        self.assertIsNotNone(pick(rows, "P1")["game_per"])

    def test_row_without_a_counted_game_has_no_per(self):
        games, boxes, players = one_game()
        boxes[0] = (boxes[0][0][:1], boxes[0][1])               # road totals missing
        rows = derive(games, boxes, players)
        self.assertEqual({r["game_per"] for r in rows}, {None})
        self.assertEqual(len(rows), len(players))


class TeamTests(unittest.TestCase):
    def test_projection_keeps_the_published_columns_only(self):
        advanced = [dict(box(1)[1][0], side=side, club_code=club, opponent_club_code=other,
                         phase_code="RS", round_number=1, load_id=7, pace=Decimal(70),
                         game_minutes=Decimal(40))
                    for side, club, other in (("road", "BAR", "MAD"), ("local", "MAD", "BAR"))]
        rows = team_rows(advanced)
        self.assertEqual([r["side"] for r in rows], ["local", "road"])
        self.assertEqual(set(rows[0]) | {"competition_code", "season_code"},
                         set(columns("game_team_advanced")))
        self.assertEqual(rows[0]["pace"], Decimal(70))
        self.assertIsNone(rows[0]["efg_pct"])


class RegistrationTests(unittest.TestCase):
    def test_tables_are_registered_with_the_contract_keys(self):
        self.assertEqual(GOLD_TABLES["game_player_advanced"].key,
                         ("competition_code", "season_code", "game_code", "side", "person_key"))
        self.assertEqual(GOLD_TABLES["game_team_advanced"].key,
                         ("competition_code", "season_code", "game_code", "side"))
        names = columns("game_player_advanced")
        self.assertEqual(names[-3:], ("game_uper", "game_aper", "game_per"))
        self.assertEqual(len(names), 21)
        self.assertEqual(len(columns("game_team_advanced")), 22)

    def test_replace_is_scoped_atomic_and_rolls_back(self):
        from gold_etl.loader import replace_aggregate_scope

        row = dict(derive(*one_game())[0], competition_code="E", season_code="E2025")
        db = FakeConnection()
        with patch("gold_etl.loader.read_aggregate_rows", return_value=[row]), \
                patch("psycopg2.extras.execute_values") as insert:
            self.assertEqual(replace_aggregate_scope(db, "game_player_advanced", "E", "E2025"), 1)
        self.assertEqual((db.commits, db.rollbacks), (1, 0))
        self.assertEqual(insert.call_args.args[2][0][:2], ("E", "E2025"))
        failing = FakeConnection()
        with patch("gold_etl.loader.read_aggregate_rows", return_value=[row]), \
                patch("psycopg2.extras.execute_values", side_effect=RuntimeError("failed")):
            with self.assertRaisesRegex(RuntimeError, "failed"):
                replace_aggregate_scope(failing, "game_player_advanced", "E", "E2025")
        self.assertEqual((failing.commits, failing.rollbacks), (0, 1))

    def test_dispatch_reads_the_requested_table(self):
        from gold_etl.loader import read_aggregate_rows

        with patch("gold_etl.loader.read_game_advanced_rows", return_value=[]) as read:
            read_aggregate_rows(None, "game_team_advanced", "E", "E2025")
        read.assert_called_once_with(None, "E", "E2025", "game_team_advanced")
        self.assertEqual(GAME_ADVANCED_NAMES, ("game_player_advanced", "game_team_advanced"))


if __name__ == "__main__":
    unittest.main()
