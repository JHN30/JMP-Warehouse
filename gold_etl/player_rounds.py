"""Cumulative player stats after every round, per scope, from Silver box scores.

Scopes are `all`, each phase, and `PS`. A player has a row for every scope round
from their first appearance on; idle rounds carry the previous values. Rates are
ratios of sums over the player's appearances, each with that game's own team, so a
mid-season transfer needs no special handling. Formulas restate feature 25's.
"""

from collections import defaultdict
from decimal import Decimal

from gold_etl.schema import PLAYER_TOTALS
from gold_etl.standings import _dict_rows
from gold_etl.team_rounds import _counted_games, _scopes, read_tables

FT_WEIGHT = Decimal("0.44")
PLACES = Decimal("0.000001")
SUMS = ("used", "usg_num", "usg_den", "ast_den", "orb_den", "drb_den", "trb_den",
        "stl_den", "blk_den", "possessions_played", "pie_num", "pie_den", "game_score")


def _num(value):
    return None if value is None else Decimal(str(value))


def _lin(*terms):
    """Sum of (coefficient, value) pairs; None when any value is missing."""
    if any(value is None for _, value in terms):
        return None
    return sum((coefficient * value for coefficient, value in terms), Decimal(0))


def _mul(a, b):
    return None if a is None or b is None else a * b


def _div(numerator, denominator):
    if numerator is None or denominator is None or denominator == 0:
        return None
    return (numerator / denominator).quantize(PLACES)


def _pie_numerator(s):
    return _lin((1, s["points"]), (1, s["field_goals_made"]), (1, s["free_throws_made"]),
                (-1, s["field_goals_attempted"]), (-1, s["free_throws_attempted"]),
                (1, s["defensive_rebounds"]), (Decimal("0.5"), s["offensive_rebounds"]),
                (1, s["assists"]), (1, s["steals"]), (Decimal("0.5"), s["blocks"]),
                (-1, s["fouls_committed"]), (-1, s["turnovers"]))


def _used(s):
    return _lin((1, s["field_goals_attempted"]), (FT_WEIGHT, s["free_throws_attempted"]),
                (1, s["turnovers"]))


def _appearance(entry, row, game_score):
    """Every additive contribution of one player game (None where an input is missing).

    `team_seconds` is the game length in seconds (a team's minutes divided by 5), so
    `share` is the fraction of the game the player was on court, as in the standard forms."""
    p = {name: _num(row.get(name)) for name in PLAYER_TOTALS}
    own = {name: _num(entry["own"].get(name)) for name in PLAYER_TOTALS}
    opp = {name: _num(entry["opp"].get(name)) for name in PLAYER_TOTALS}
    seconds = p["seconds_played"]
    team_seconds = None if entry["minutes"] is None else Decimal(str(entry["minutes"])) * 60
    poss = _num(entry["possessions"])
    share = None if seconds is None or not team_seconds else seconds / team_seconds
    used, team_used = _used(p), _used(own)
    opp_two = _lin((1, opp["field_goals_attempted"]), (-1, opp["three_pointers_attempted"]))
    game_pie = None
    own_pie, opp_pie = _pie_numerator(own), _pie_numerator(opp)
    if own_pie is not None and opp_pie is not None:
        game_pie = own_pie + opp_pie

    def rebound(mine, team, theirs):
        return _mul(share, _lin((1, team[mine]), (1, theirs)))

    contributions = dict(p)
    contributions.update(
        used=used, usg_num=_mul(used, team_seconds), usg_den=_mul(seconds, team_used),
        ast_den=_lin((1, _mul(share, own["field_goals_made"])),
                     (-1, p["field_goals_made"])),
        orb_den=rebound("offensive_rebounds", own, opp["defensive_rebounds"]),
        drb_den=rebound("defensive_rebounds", own, opp["offensive_rebounds"]),
        trb_den=rebound("total_rebounds", own, opp["total_rebounds"]),
        stl_den=_mul(share, poss), blk_den=_mul(share, opp_two),
        possessions_played=_mul(share, poss),
        pie_num=_pie_numerator(p), pie_den=game_pie, game_score=_num(game_score))
    contributions["started"] = 1 if row.get("started") else 0
    return contributions


def _ratios(state):
    def ratio(numerator, denominator):
        return _div(state[numerator], state[denominator])

    def per_100(name):
        return _div(None if state[name] is None else 100 * state[name],
                    state["possessions_played"])

    true_shooting_den = _lin((2, state["field_goals_attempted"]),
                             (2 * FT_WEIGHT, state["free_throws_attempted"]))
    efg_num = _lin((1, state["field_goals_made"]), (Decimal("0.5"), state["three_pointers_made"]))
    games = state["games_played"]
    return {
        "ts_pct": _div(state["points"], true_shooting_den),
        "efg_pct": _div(efg_num, state["field_goals_attempted"]),
        "usg_pct": ratio("usg_num", "usg_den"), "ast_pct": _div(state["assists"], state["ast_den"]),
        "orb_pct": _div(state["offensive_rebounds"], state["orb_den"]),
        "drb_pct": _div(state["defensive_rebounds"], state["drb_den"]),
        "trb_pct": _div(state["total_rebounds"], state["trb_den"]),
        "stl_pct": _div(state["steals"], state["stl_den"]),
        "blk_pct": _div(state["blocks"], state["blk_den"]),
        "tov_pct": _div(state["turnovers"], state["used"]),
        "possessions_played": None if state["possessions_played"] is None
        else state["possessions_played"].quantize(PLACES),
        "points_per_100": per_100("points"), "rebounds_per_100": per_100("total_rebounds"),
        "assists_per_100": per_100("assists"), "steals_per_100": per_100("steals"),
        "blocks_per_100": per_100("blocks"), "turnovers_per_100": per_100("turnovers"),
        "game_score_total": None if state["game_score"] is None
        else state["game_score"].quantize(PLACES),
        "game_score_average": _div(state["game_score"], Decimal(games)) if games else None,
        "pie": ratio("pie_num", "pie_den"),
    }


def derive_rows(games, team_stats, advanced, clubs, player_stats, player_advanced):
    """Rows for `player_round_stats`, sorted by scope, round and player."""
    entries = _counted_games(games, team_stats, advanced)
    by_side = {(entry["game_code"], "local" if entry["home"] else "road"): entry
               for entry in entries}
    scores = {(row["game_code"], row["side"], row["person_key"]): row.get("game_score")
              for row in player_advanced}
    rounds_by_scope = defaultdict(set)
    for entry in entries:
        for scope in _scopes(entry["phase"], entry["season"]):
            rounds_by_scope[scope].add(entry["round"])
    appearances = defaultdict(lambda: defaultdict(list))   # scope -> player -> [(entry, row)]
    for row in player_stats:
        entry = by_side.get((row["game_code"], row["side"]))
        seconds = row.get("seconds_played")
        if entry is None or seconds is None or seconds <= 0:
            continue
        for scope in _scopes(entry["phase"], entry["season"]):
            appearances[scope][row["person_key"]].append((entry, row))
    rows = []
    for scope in sorted(appearances):
        for person, played in sorted(appearances[scope].items()):
            played.sort(key=lambda pair: (pair[0]["round"], pair[0]["game_code"]))
            state = {name: Decimal(0) for name in PLAYER_TOTALS + SUMS}
            state.update(games_played=0, games_started=0)
            latest, pending = None, iter(played)
            upcoming = next(pending, None)
            for number in (r for r in sorted(rounds_by_scope[scope])
                           if r >= played[0][0]["round"]):
                while upcoming is not None and upcoming[0]["round"] <= number:
                    entry, row = upcoming
                    contribution = _appearance(
                        entry, row, scores.get((row["game_code"], row["side"], person)))
                    state["games_played"] += 1
                    state["games_started"] += contribution.pop("started")
                    for name, value in contribution.items():
                        state[name] = (None if state[name] is None or value is None
                                       else state[name] + value)
                    latest = row
                    upcoming = next(pending, None)
                out = {"scope": scope, "round_number": number, "person_key": person,
                       "club_code": latest.get("club_code"),
                       "player_name": latest.get("person_name"),
                       "games_played": state["games_played"],
                       "games_started": state["games_started"]}
                for name in PLAYER_TOTALS:
                    out[name] = state[name]
                out.update(_ratios(state))
                rows.append(out)
    rows.sort(key=lambda r: (r["scope"], r["round_number"], r["person_key"]))
    return rows


def read_rows(cursor, competition_code, season_code):
    scope = (competition_code, season_code)
    extra = []
    for table in ("game_player_stats", "game_player_advanced"):
        cursor.execute(f"SELECT * FROM silver.{table} WHERE competition_code = %s "
                       "AND season_code = %s", scope)
        extra.append(_dict_rows(cursor))
    return derive_rows(*read_tables(cursor, competition_code, season_code), *extra)
