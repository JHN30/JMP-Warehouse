"""Cumulative Win Shares after every round, per scope (Basketball-Reference method).

Scopes are `all`, each phase, and `PS`. A player has a row for every scope round from
their first appearance on. Player, club and opponent totals are summed over the games
the player appeared in (each with that game's own club); league constants are summed over
every counted game of the scope through the round. Undefined ratios give NULL; the few
bracketed terms that multiply a zero count contribute 0 (see `_zero_safe`).
"""

from collections import defaultdict
from decimal import Decimal, DecimalException

from gold_etl.player_rounds import _num
from gold_etl.standings import _dict_rows
from gold_etl.team_rounds import _counted_games, _scopes, read_tables

PLACES = Decimal("0.000001")
HALF = Decimal("0.5")
PLAYER_FIELDS = {"pts": "points", "fg": "field_goals_made", "fga": "field_goals_attempted",
                 "tp": "three_pointers_made", "ft": "free_throws_made",
                 "fta": "free_throws_attempted", "orb": "offensive_rebounds",
                 "drb": "defensive_rebounds", "ast": "assists", "stl": "steals",
                 "blk": "blocks", "tov": "turnovers", "pf": "fouls_committed"}
TEAM_KEYS = ("pts", "fg", "fga", "tp", "ft", "fta", "orb", "drb", "ast", "tov", "stl",
             "blk", "pf")
OPP_FIELDS = {"pts": "points", "fg": "field_goals_made", "fga": "field_goals_attempted",
              "ft": "free_throws_made", "fta": "free_throws_attempted",
              "orb": "offensive_rebounds", "drb": "defensive_rebounds",
              "trb": "total_rebounds", "tov": "turnovers"}
STATE_KEYS = (("seconds", *PLAYER_FIELDS), tuple(f"t_{k}" for k in TEAM_KEYS),
              tuple(f"o_{k}" for k in OPP_FIELDS), ("t_poss", "t_minutes"))
ALL_KEYS = tuple(key for group in STATE_KEYS for key in group)


class _Undefined(Exception):
    """A required ratio has a zero denominator."""


def _add(total, value):
    return None if total is None or value is None else total + value


def _div(numerator, denominator):
    if denominator == 0:
        raise _Undefined
    return numerator / denominator


def _zero_safe(numerator, denominator):
    """A bracketed ratio that multiplies a zero count when its denominator is zero."""
    return Decimal(0) if denominator == 0 else numerator / denominator


def _league_states(entries):
    """Cumulative league sums after each round of one scope: {round: state}."""
    by_round = defaultdict(list)
    for entry in entries:
        by_round[entry["round"]].append(entry)
    state = {"pts": Decimal(0), "poss": Decimal(0), "minutes": Decimal(0), "games": 0}
    states = {}
    for number in sorted(by_round):
        for entry in by_round[number]:
            state["pts"] = _add(state["pts"], _num(entry["own"].get("points")))
            state["poss"] = _add(state["poss"], _num(entry["possessions"]))
            state["minutes"] = _add(state["minutes"], _num(entry["minutes"]))
            state["games"] += 1
        states[number] = dict(state)
    return states


def _league(state):
    """lgPTS per possession, per team game and pace; None when undefined."""
    if state is None or any(value is None for value in state.values()):
        return None
    try:
        return {"ppp": _div(state["pts"], state["poss"]),
                "ppg": _div(state["pts"], state["games"]),
                "pace": _div(40 * state["poss"], state["minutes"])}
    except _Undefined:
        return None


def _complete(s):
    return all(s[key] is not None for key in ALL_KEYS)


def _marginal_ppw(s, league):
    team_pace = _div(40 * s["t_poss"], s["t_minutes"])
    return Decimal("0.32") * league["ppg"] * team_pace / league["pace"]


def _offense(s, league):
    """Offensive Win Shares and its named intermediates (None when undefined)."""
    if league is None or not _complete(s):
        return None
    mp = s["seconds"] / 60
    team_mp = 5 * s["t_minutes"]
    try:
        pf_share = _zero_safe(s["pts"] - s["ft"], 2 * s["fga"])
        qast = (mp / (team_mp / 5) * (Decimal("1.14") * _div(s["t_ast"] - s["ast"], s["t_fg"]))
                + _div(s["t_ast"] / team_mp * mp * 5 - s["ast"],
                       s["t_fg"] / team_mp * mp * 5 - s["fg"]) * (1 - mp / (team_mp / 5)))
        fg_part = s["fg"] * (1 - HALF * pf_share * qast)
        team_ft = 1 - _zero_safe(s["t_ft"], s["t_fta"])
        ast_share = _zero_safe((s["t_pts"] - s["t_ft"]) - (s["pts"] - s["ft"]),
                               2 * (s["t_fga"] - s["fga"]))
        ast_part = HALF * ast_share * s["ast"]
        own_ft = 1 - _zero_safe(s["ft"], s["fta"])
        ft_part = (1 - own_ft ** 2) * Decimal("0.4") * s["fta"]
        team_scoring = s["t_fg"] + (1 - team_ft ** 2) * s["t_fta"] * Decimal("0.4")
        team_orb = _div(s["t_orb"], s["t_orb"] + (s["o_trb"] - s["o_orb"]))
        team_play = _div(team_scoring, s["t_fga"] + s["t_fta"] * Decimal("0.4") + s["t_tov"])
        weight = _div((1 - team_orb) * team_play,
                      (1 - team_orb) * team_play + team_orb * (1 - team_play))
        orb_part = s["orb"] * weight * team_play
        shrink = 1 - _div(s["t_orb"], team_scoring) * weight * team_play
        scoring = (fg_part + ast_part + ft_part) * shrink + orb_part
        fg_miss = (s["fga"] - s["fg"]) * (1 - Decimal("1.07") * team_orb)
        ft_miss = own_ft ** 2 * Decimal("0.4") * s["fta"]
        possessions = scoring + fg_miss + ft_miss + s["tov"]
        pprod_fg = 2 * (s["fg"] + HALF * s["tp"]) * (1 - HALF * pf_share * qast)
        others = _zero_safe(s["t_fg"] - s["fg"] + HALF * (s["t_tp"] - s["tp"]),
                            s["t_fg"] - s["fg"])
        pprod_ast = 2 * others * HALF * ast_share * s["ast"]
        pprod_orb = s["orb"] * weight * team_play * _div(s["t_pts"], team_scoring)
        pprod = (pprod_fg + pprod_ast + s["ft"]) * shrink + pprod_orb
        marginal = pprod - Decimal("0.92") * league["ppp"] * possessions
        return {"qast": qast, "fg_part": fg_part, "ast_part": ast_part, "ft_part": ft_part,
                "scposs": scoring, "totposs": possessions, "pprod": pprod,
                "off_ws": marginal / _marginal_ppw(s, league)}
    except (_Undefined, DecimalException):
        return None


def _defense(s, league):
    """Defensive Win Shares and its named intermediates (None when undefined)."""
    if league is None or not _complete(s):
        return None
    mp = s["seconds"] / 60
    team_mp = 5 * s["t_minutes"]
    try:
        dor = _div(s["o_orb"], s["o_orb"] + s["t_drb"])
        dfg = _div(s["o_fg"], s["o_fga"])
        weight = _div(dfg * (1 - dor), dfg * (1 - dor) + (1 - dfg) * dor)
        stops1 = (s["stl"] + s["blk"] * weight * (1 - Decimal("1.07") * dor)
                  + s["drb"] * (1 - weight))
        opp_ft = 1 - _zero_safe(s["o_ft"], s["o_fta"])
        stops2 = ((_div(s["o_fga"] - s["o_fg"] - s["t_blk"], team_mp) * weight
                   * (1 - Decimal("1.07") * dor) + _div(s["o_tov"] - s["t_stl"], team_mp))
                  * mp + _div(s["pf"], s["t_pf"]) * Decimal("0.4") * s["o_fta"] * opp_ft ** 2)
        stops = stops1 + stops2
        stop_pct = _div(stops * team_mp, s["t_poss"] * mp)
        team_drtg = _div(100 * s["o_pts"], s["t_poss"])
        per_scoring = _div(s["o_pts"], s["o_fg"] + (1 - opp_ft ** 2) * s["o_fta"]
                           * Decimal("0.4"))
        drtg = team_drtg + Decimal("0.2") * (100 * per_scoring * (1 - stop_pct) - team_drtg)
        marginal = (mp / team_mp) * s["t_poss"] * (Decimal("1.08") * league["ppp"]
                                                   - drtg / 100)
        return {"stops1": stops1, "stops2": stops2, "stop_pct": stop_pct, "drtg": drtg,
                "def_ws": marginal / _marginal_ppw(s, league)}
    except (_Undefined, DecimalException):
        return None


def _values(s, league):
    offense, defense = _offense(s, league), _defense(s, league)
    off = None if offense is None else offense["off_ws"]
    dfn = None if defense is None else defense["def_ws"]
    total = None if off is None or dfn is None else off + dfn
    per_40 = None if total is None else total * 40 / (s["seconds"] / 60)
    return {"off_win_shares": off, "def_win_shares": dfn, "win_shares": total,
            "win_shares_per_40": per_40}


def _fresh():
    return {key: Decimal(0) for key in ALL_KEYS}


def _accumulate(state, entry, row):
    values = {"seconds": _num(row.get("seconds_played"))}
    values.update({key: _num(row.get(field)) for key, field in PLAYER_FIELDS.items()})
    values.update({f"t_{key}": _num(entry["own"].get(PLAYER_FIELDS[key]))
                   for key in TEAM_KEYS})
    values.update({f"o_{key}": _num(entry["opp"].get(field))
                   for key, field in OPP_FIELDS.items()})
    values.update(t_poss=_num(entry["possessions"]), t_minutes=_num(entry["minutes"]))
    for key, value in values.items():
        state[key] = _add(state[key], value)


def derive_rows(games, team_stats, advanced, clubs, player_stats):
    """Rows for `player_round_win_shares`, sorted by scope, round and player."""
    entries = _counted_games(games, team_stats, advanced)
    by_side = {(entry["game_code"], "local" if entry["home"] else "road"): entry
               for entry in entries}
    scope_entries = defaultdict(list)
    for entry in entries:
        for scope in _scopes(entry["phase"], entry["season"]):
            scope_entries[scope].append(entry)
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
        states = _league_states(scope_entries[scope])
        leagues = {number: _league(state) for number, state in states.items()}
        for person, played in appearances[scope].items():
            played.sort(key=lambda pair: (pair[0]["round"], pair[0]["game_code"]))
            state, games_played, latest, upcoming = _fresh(), 0, None, 0
            for number in (r for r in sorted(states) if r >= played[0][0]["round"]):
                while upcoming < len(played) and played[upcoming][0]["round"] <= number:
                    entry, row = played[upcoming]
                    _accumulate(state, entry, row)
                    games_played += 1
                    latest, upcoming = row, upcoming + 1
                row = {"scope": scope, "round_number": number, "person_key": person,
                       "club_code": latest.get("club_code"),
                       "player_name": latest.get("person_name"),
                       "games_played": games_played, "seconds_played": state["seconds"]}
                for name, value in _values(state, leagues[number]).items():
                    row[name] = None if value is None else value.quantize(PLACES)
                rows.append(row)
    rows.sort(key=lambda r: (r["scope"], r["round_number"], r["person_key"]))
    return rows


def read_rows(cursor, competition_code, season_code):
    cursor.execute("SELECT * FROM silver.game_player_stats WHERE competition_code = %s "
                   "AND season_code = %s", (competition_code, season_code))
    players = _dict_rows(cursor)   # before read_tables, which reuses the cursor
    return derive_rows(*read_tables(cursor, competition_code, season_code), players)
