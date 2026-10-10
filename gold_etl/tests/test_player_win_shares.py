"""Cumulative Win Shares: intermediates, offense, defense, edge cases, storage, quality."""

import unittest
from decimal import Decimal
from unittest.mock import patch

from gold_etl.player_win_shares import (_accumulate, _defense, _fresh, _league, _offense,
                                        derive_rows)
from gold_etl.tests.test_player_rounds import (LOCAL, ROAD, STAR, FakeConnection, box, game,
                                               minus, player)

FIELDS = {"pts": "points", "fg": "field_goals_made", "fga": "field_goals_attempted",
          "tp": "three_pointers_made", "ft": "free_throws_made", "fta": "free_throws_attempted",
          "orb": "offensive_rebounds", "drb": "defensive_rebounds", "ast": "assists",
          "stl": "steals", "blk": "blocks", "tov": "turnovers", "pf": "fouls_committed",
          "trb": "total_rebounds"}


def short(stats):
    return {key: float(stats[field]) for key, field in FIELDS.items()}


def reference(p, seconds, team, opp, team_poss, team_min, league):
    """Basketball-Reference Win Shares written out with floats (independent of the module)."""
    mp, team_mp = seconds / 60, 5 * team_min
    q_ast = (mp / (team_mp / 5) * (1.14 * (team["ast"] - p["ast"]) / team["fg"])
             + ((team["ast"] / team_mp * mp * 5 - p["ast"])
                / (team["fg"] / team_mp * mp * 5 - p["fg"])) * (1 - mp / (team_mp / 5)))
    pf_share = (p["pts"] - p["ft"]) / (2 * p["fga"]) if p["fga"] else 0
    fg_part = p["fg"] * (1 - 0.5 * pf_share * q_ast)
    ast_share = (((team["pts"] - team["ft"]) - (p["pts"] - p["ft"]))
                 / (2 * (team["fga"] - p["fga"])))
    ast_part = 0.5 * ast_share * p["ast"]
    ft_pct = p["ft"] / p["fta"] if p["fta"] else 0
    ft_part = (1 - (1 - ft_pct) ** 2) * 0.4 * p["fta"]
    team_ft = team["ft"] / team["fta"] if team["fta"] else 0
    team_scoring = team["fg"] + (1 - (1 - team_ft) ** 2) * team["fta"] * 0.4
    team_orb = team["orb"] / (team["orb"] + (opp["trb"] - opp["orb"]))
    team_play = team_scoring / (team["fga"] + team["fta"] * 0.4 + team["tov"])
    weight = ((1 - team_orb) * team_play) / ((1 - team_orb) * team_play
                                              + team_orb * (1 - team_play))
    shrink = 1 - (team["orb"] / team_scoring) * weight * team_play
    sc_poss = ((fg_part + ast_part + ft_part) * shrink + p["orb"] * weight * team_play)
    tot_poss = (sc_poss + (p["fga"] - p["fg"]) * (1 - 1.07 * team_orb)
                + (1 - ft_pct) ** 2 * 0.4 * p["fta"] + p["tov"])
    pprod_fg = 2 * (p["fg"] + 0.5 * p["tp"]) * (1 - 0.5 * pf_share * q_ast)
    others = ((team["fg"] - p["fg"] + 0.5 * (team["tp"] - p["tp"])) / (team["fg"] - p["fg"]))
    pprod_ast = 2 * others * 0.5 * ast_share * p["ast"]
    pprod_orb = p["orb"] * weight * team_play * (team["pts"] / team_scoring)
    pprod = (pprod_fg + pprod_ast + p["ft"]) * shrink + pprod_orb
    ppw = 0.32 * league["ppg"] * (40 * team_poss / team_min) / league["pace"]
    off_ws = (pprod - 0.92 * league["ppp"] * tot_poss) / ppw
    dor = opp["orb"] / (opp["orb"] + team["drb"])
    dfg = opp["fg"] / opp["fga"]
    fmwt = dfg * (1 - dor) / (dfg * (1 - dor) + (1 - dfg) * dor)
    stops1 = p["stl"] + p["blk"] * fmwt * (1 - 1.07 * dor) + p["drb"] * (1 - fmwt)
    opp_ft = opp["ft"] / opp["fta"] if opp["fta"] else 0
    stops2 = (((opp["fga"] - opp["fg"] - team["blk"]) / team_mp * fmwt * (1 - 1.07 * dor)
               + (opp["tov"] - team["stl"]) / team_mp) * mp
              + (p["pf"] / team["pf"]) * 0.4 * opp["fta"] * (1 - opp_ft) ** 2)
    stop_pct = (stops1 + stops2) * team_mp / (team_poss * mp)
    team_drtg = 100 * opp["pts"] / team_poss
    per_scoring = opp["pts"] / (opp["fg"] + (1 - (1 - opp_ft) ** 2) * opp["fta"] * 0.4)
    drtg = team_drtg + 0.2 * (100 * per_scoring * (1 - stop_pct) - team_drtg)
    def_ws = (mp / team_mp * team_poss * (1.08 * league["ppp"] - drtg / 100)) / ppw
    return {"qast": q_ast, "fg_part": fg_part, "ast_part": ast_part, "ft_part": ft_part,
            "scposs": sc_poss, "totposs": tot_poss, "pprod": pprod, "off_ws": off_ws,
            "stops1": stops1, "stops2": stops2, "stop_pct": stop_pct, "drtg": drtg,
            "def_ws": def_ws}


def derive(games, boxes, players):
    stats = [row for rows, _ in boxes for row in rows]
    advanced = [row for _, rows in boxes for row in rows]
    return derive_rows(games, stats, advanced, [], players)


def pick(rows, scope, round_number, key):
    return next(row for row in rows if (row["scope"], row["round_number"], row["person_key"])
                == (scope, round_number, key))


def one_game(code=1, round_number=1, phase="RS", star_seconds=1200):
    bench = dict(minus(LOCAL, STAR), seconds_played=12000 - star_seconds)
    players = [player(code, "P1", started=True, **dict(STAR, seconds_played=star_seconds)),
               player(code, "P2", **bench),
               player(code, "R1", side="road", club="BAR", **dict(ROAD, seconds_played=12000))]
    return [game(code, round_number, phase=phase)], [box(code)], players


def state_for(local=LOCAL, road=ROAD, star=STAR, seconds=1200, poss=70.42, minutes=40):
    """Accumulated state of the star (home side) over one game."""
    entry = {"own": local, "opp": road, "possessions": Decimal(str(poss)),
             "minutes": Decimal(minutes)}
    state = _fresh()
    _accumulate(state, entry, dict(star, seconds_played=seconds))
    return state


LEAGUE = {"ppp": 157 / 140.84, "ppg": 157 / 2, "pace": 70.42}
LEAGUE_STATE = {"pts": Decimal(157), "poss": Decimal("140.84"), "minutes": Decimal(80),
                "games": 2}


class FormulaTests(unittest.TestCase):
    def test_league_constants(self):
        league = _league(LEAGUE_STATE)
        self.assertAlmostEqual(float(league["ppp"]), LEAGUE["ppp"], places=6)
        self.assertAlmostEqual(float(league["ppg"]), LEAGUE["ppg"], places=6)
        self.assertAlmostEqual(float(league["pace"]), LEAGUE["pace"], places=6)
        self.assertIsNone(_league(dict(LEAGUE_STATE, poss=Decimal(0))))
        self.assertIsNone(_league(dict(LEAGUE_STATE, pts=None)))

    def test_offense_intermediates_and_win_shares_match_the_reference(self):
        expected = reference(short(STAR), 1200, short(LOCAL), short(ROAD), 70.42, 40, LEAGUE)
        got = _offense(state_for(), _league(LEAGUE_STATE))
        for name in ("qast", "fg_part", "ast_part", "ft_part", "scposs", "totposs", "pprod",
                     "off_ws"):
            self.assertAlmostEqual(float(got[name]), expected[name], places=4, msg=name)

    def test_defense_intermediates_and_win_shares_match_the_reference(self):
        expected = reference(short(STAR), 1200, short(LOCAL), short(ROAD), 70.42, 40, LEAGUE)
        got = _defense(state_for(), _league(LEAGUE_STATE))
        for name in ("stops1", "stops2", "stop_pct", "drtg", "def_ws"):
            self.assertAlmostEqual(float(got[name]), expected[name], places=4, msg=name)

    def test_row_combines_offense_defense_and_per_40(self):
        rows = derive(*one_game())
        star = pick(rows, "all", 1, "P1")
        expected = reference(short(STAR), 1200, short(LOCAL), short(ROAD), 70.42, 40, LEAGUE)
        total = expected["off_ws"] + expected["def_ws"]
        self.assertAlmostEqual(float(star["off_win_shares"]), expected["off_ws"], places=4)
        self.assertAlmostEqual(float(star["def_win_shares"]), expected["def_ws"], places=4)
        self.assertAlmostEqual(float(star["win_shares"]), total, places=4)
        self.assertAlmostEqual(float(star["win_shares_per_40"]), total * 40 / 20, places=4)
        self.assertEqual((star["games_played"], star["seconds_played"]), (1, 1200))

    def test_player_with_no_free_throws_or_field_goals_is_not_null(self):
        quiet = dict(BASE_ZERO(), seconds_played=600, steals=1, turnovers=1)
        state = state_for(star=quiet, seconds=600)
        league = _league(LEAGUE_STATE)
        self.assertIsNotNone(_offense(state, league))
        self.assertIsNotNone(_defense(state, league))
        expected = reference(short(quiet), 600, short(LOCAL), short(ROAD), 70.42, 40, LEAGUE)
        self.assertAlmostEqual(float(_offense(state, league)["off_ws"]), expected["off_ws"],
                               places=4)

    def test_missing_input_and_undefined_ratios_are_null(self):
        league = _league(LEAGUE_STATE)
        state = state_for()
        state["ast"] = None
        self.assertIsNone(_offense(state, league))
        self.assertIsNone(_defense(state, league))
        empty = state_for(local=dict(LOCAL, field_goals_made=0))
        self.assertIsNone(_offense(empty, league))           # team field goals: divide by zero
        self.assertIsNone(_offense(state_for(), None))


def BASE_ZERO():
    return {key: 0 for key in STAR}


class RowTests(unittest.TestCase):
    def test_transfer_keeps_one_row_with_the_latest_club_and_each_games_own_context(self):
        games, boxes, players = one_game()
        games += [game(2, 2, local="BAR", road="MAD")]
        boxes += [box(2, local=ROAD, road=LOCAL, possessions="80")]
        players += [player(2, "P1", club="BAR", **dict(STAR, seconds_played=1500))]
        rows = [r for r in derive(games, boxes, players)
                if r["scope"] == "all" and r["person_key"] == "P1"]
        self.assertEqual([r["club_code"] for r in rows], ["MAD", "BAR"])
        self.assertEqual(rows[-1]["games_played"], 2)
        self.assertIsNotNone(rows[-1]["win_shares"])

    def test_idle_rounds_carry_totals_but_use_that_rounds_league_constants(self):
        games, boxes, players = one_game()
        games += [game(2, 2, local="BAR", road="MAD")]
        boxes += [box(2, local=dict(ROAD, points=120), road=LOCAL, possessions="80")]
        players += [player(2, "R1", side="local", club="BAR",
                           **dict(ROAD, seconds_played=12000))]
        rows = derive(games, boxes, players)
        first, carried = pick(rows, "all", 1, "P1"), pick(rows, "all", 2, "P1")
        self.assertEqual((carried["games_played"], carried["seconds_played"]), (1, 1200))
        self.assertNotEqual(first["win_shares"], carried["win_shares"])
        self.assertIsNone(next((r for r in rows if r["round_number"] == 1
                                and r["person_key"] == "R2"), None))

    def test_scopes_and_did_not_play(self):
        games, boxes, players = one_game(phase="PO")
        players.append(player(1, "DNP", seconds_played=0))
        rows = derive(games, boxes, players)
        self.assertEqual({r["scope"] for r in rows}, {"all", "PO", "PS"})
        self.assertFalse([r for r in rows if r["person_key"] == "DNP"])

    def test_missing_player_stat_makes_that_players_row_null_only(self):
        games, boxes, players = one_game()
        players[0]["assists"] = None
        rows = derive(games, boxes, players)
        star = pick(rows, "all", 1, "P1")
        self.assertEqual((star["off_win_shares"], star["win_shares"],
                          star["win_shares_per_40"]), (None, None, None))
        self.assertIsNotNone(pick(rows, "all", 1, "P2")["win_shares"])


def stored_row():
    return dict(derive(*one_game())[0], competition_code="E", season_code="E2025")


class StorageTests(unittest.TestCase):
    def test_replace_is_scoped_atomic_and_rolls_back(self):
        from gold_etl.loader import replace_aggregate_scope

        db = FakeConnection()
        with patch("gold_etl.loader.read_aggregate_rows", return_value=[stored_row()]), \
                patch("psycopg2.extras.execute_values") as insert:
            self.assertEqual(replace_aggregate_scope(db, "player_round_win_shares", "E",
                                                     "E2025"), 1)
        self.assertEqual((db.commits, db.rollbacks), (1, 0))
        self.assertTrue(any(query.startswith('DELETE FROM gold."app_player_round_win_shares"')
                            and params == ("E", "E2025") for query, params in db.queries))
        self.assertEqual(insert.call_args.args[2][0][:2], ("E", "E2025"))
        failing = FakeConnection()
        with patch("gold_etl.loader.read_aggregate_rows", return_value=[stored_row()]), \
                patch("psycopg2.extras.execute_values", side_effect=RuntimeError("failed")):
            with self.assertRaisesRegex(RuntimeError, "failed"):
                replace_aggregate_scope(failing, "player_round_win_shares", "E", "E2025")
        self.assertEqual((failing.commits, failing.rollbacks), (0, 1))

    def test_read_rows_fetches_players_before_read_tables_reuses_the_cursor(self):
        from gold_etl import player_win_shares
        from gold_etl.loader import read_aggregate_rows

        order = []
        games, boxes, players = one_game()
        tables = [games, [r for rows, _ in boxes for r in rows],
                  [r for _, rows in boxes for r in rows], []]

        def fetch(cursor):
            order.append("fetch")
            return players

        def tables_read(*_):
            order.append("tables")
            return tables

        with patch.object(player_win_shares, "read_tables", side_effect=tables_read), \
                patch.object(player_win_shares, "_dict_rows", side_effect=fetch):
            rows = read_aggregate_rows(FakeConnection().cursor(), "player_round_win_shares",
                                       "E", "E2025")
        self.assertEqual(order, ["fetch", "tables"])
        self.assertTrue(rows)

    def test_quality_compares_a_fresh_derivation(self):
        from gold_etl.quality import check_aggregate_scope

        db, expected = FakeConnection(), stored_row()
        cursor = db.cursor()
        with patch("gold_etl.quality.read_aggregate_rows", return_value=[expected]):
            for actual, message in (([], "keys differ"),
                                    ([dict(expected, win_shares=Decimal(99))], "values differ"),
                                    ([expected], None)):
                with patch("gold_etl.quality._dict_rows", return_value=actual):
                    issues = check_aggregate_scope(cursor, "player_round_win_shares", "E",
                                                   "E2025")
                    self.assertEqual(issues == [], message is None)
                    if message:
                        self.assertIn(message, issues[0])


class LeagueTotalTests(unittest.TestCase):
    def warnings(self, totals, games_played):
        from gold_etl.quality import check_round_win_share_totals

        ws = [{"scope": "all", "round_number": n, "win_shares": Decimal(str(v))}
              for n, v in totals.items()]
        stats = [{"scope": "all", "round_number": n, "games_played": g}
                 for n, g in games_played.items()]
        with patch("gold_etl.quality._dict_rows", side_effect=[ws, stats]):
            return check_round_win_share_totals(FakeConnection().cursor(), "E", "E2025")

    def test_close_totals_and_small_samples_report_nothing(self):
        self.assertEqual(self.warnings({1: 41, 2: 3}, {1: 80, 2: 10}), [])  # 40 games; 5 games

    def test_a_total_far_from_the_games_is_reported(self):
        warnings = self.warnings({1: 40}, {1: 80})                          # 40 games, 40 WS
        self.assertEqual(warnings, [])
        warnings = self.warnings({1: 60}, {1: 80})
        self.assertEqual(len(warnings), 1)
        self.assertIn("win shares total 60.0 for 40 games", warnings[0])

    def test_null_win_shares_are_left_out(self):
        from gold_etl.quality import check_round_win_share_totals

        ws = [{"scope": "all", "round_number": 1, "win_shares": None}]
        with patch("gold_etl.quality._dict_rows", side_effect=[ws, []]):
            self.assertEqual(check_round_win_share_totals(FakeConnection().cursor(), "E",
                                                          "E2025"), [])


if __name__ == "__main__":
    unittest.main()
