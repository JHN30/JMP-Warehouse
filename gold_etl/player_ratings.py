"""Cumulative Player Efficiency Rating after every round, per scope.

Scopes are `all`, each phase, and `PS`. A player has a row for every scope round from
their first appearance on. League constants are recomputed each round from the scope's
counted games (both clubs of every game); the player's team context (assists, field
goals, pace) comes from the games the player appeared in, each with that game's own club.
`per` is normalized so the seconds-weighted league mean is 15.
"""

from collections import defaultdict
from decimal import Decimal

from gold_etl.player_rounds import _num
from gold_etl.standings import _dict_rows
from gold_etl.team_rounds import _counted_games, _scopes, read_tables

PLACES = Decimal("0.000001")
FT_WEIGHT = Decimal("0.44")
AVERAGE = Decimal(15)
LEAGUE = ("points", "field_goals_made", "field_goals_attempted", "free_throws_made",
          "free_throws_attempted", "offensive_rebounds", "total_rebounds", "assists",
          "turnovers", "fouls_committed")
PLAYER = ("seconds_played", "three_pointers_made", "assists", "field_goals_made",
          "field_goals_attempted", "free_throws_made", "free_throws_attempted",
          "turnovers", "total_rebounds", "offensive_rebounds", "steals", "blocks",
          "fouls_committed")
CONTEXT = ("team_assists", "team_field_goals", "team_possessions", "team_minutes")


def _add(total, value):
    return None if total is None or value is None else total + value


def _div(numerator, denominator):
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def _league_states(entries):
    """Cumulative league sums after each round of one scope: {round: state}."""
    by_round = defaultdict(list)
    for entry in entries:
        by_round[entry["round"]].append(entry)
    state = {name: Decimal(0) for name in (*LEAGUE, "possessions", "minutes")}
    states = {}
    for number in sorted(by_round):
        for entry in by_round[number]:
            for name in LEAGUE:
                state[name] = _add(state[name], _num(entry["own"].get(name)))
            state["possessions"] = _add(state["possessions"], _num(entry["possessions"]))
            state["minutes"] = _add(state["minutes"], _num(entry["minutes"]))
        states[number] = dict(state)
    return states


def _constants(league):
    """factor, VOP, DRB% and pace for one league state (None when undefined)."""
    if any(value is None for value in league.values()):
        return None
    fgm, ftm, ast = (league["field_goals_made"], league["free_throws_made"],
                     league["assists"])
    if not fgm or not ftm:
        return None
    factor = Decimal(2) / 3 - (Decimal("0.5") * ast / fgm) / (2 * fgm / ftm)
    vop = _div(league["points"], league["field_goals_attempted"] - league["offensive_rebounds"]
               + league["turnovers"] + FT_WEIGHT * league["free_throws_attempted"])
    drb = _div(league["total_rebounds"] - league["offensive_rebounds"],
               league["total_rebounds"])
    pace = _div(40 * league["possessions"], league["minutes"])
    if None in (vop, drb, pace) or not league["fouls_committed"]:
        return None
    return {"factor": factor, "vop": vop, "drb": drb, "pace": pace,
            "foul": league["free_throws_made"] / league["fouls_committed"]
            - FT_WEIGHT * league["free_throws_attempted"] / league["fouls_committed"] * vop}


def _uper(s, c):
    """Unadjusted PER and the player's pace-adjusted value; None when undefined."""
    if c is None or any(s[name] is None for name in (*PLAYER, *CONTEXT)):
        return None, None
    minutes = s["seconds_played"] / 60
    team_fg, team_ast = s["team_field_goals"], s["team_assists"]
    if not minutes or not team_fg:
        return None, None
    ratio = team_ast / team_fg
    vop, drb = c["vop"], c["drb"]
    total = (3 * s["three_pointers_made"] + Decimal(2) / 3 * s["assists"]
             + (2 - c["factor"] * ratio) * s["field_goals_made"]
             + Decimal("0.5") * s["free_throws_made"] * (2 - ratio / 3)
             - vop * s["turnovers"]
             - vop * drb * (s["field_goals_attempted"] - s["field_goals_made"])
             - vop * FT_WEIGHT * (FT_WEIGHT + Decimal("0.56") * drb)
             * (s["free_throws_attempted"] - s["free_throws_made"])
             + vop * (1 - drb) * (s["total_rebounds"] - s["offensive_rebounds"])
             + vop * drb * s["offensive_rebounds"] + vop * s["steals"]
             + vop * drb * s["blocks"] - s["fouls_committed"] * c["foul"])
    uper = total / minutes
    team_pace = _div(40 * s["team_possessions"], s["team_minutes"])
    if not team_pace:
        return uper, None
    return uper, uper * c["pace"] / team_pace


def derive_rows(games, team_stats, advanced, clubs, player_stats):
    """Rows for `player_round_ratings`, sorted by scope, round and player."""
    entries = _counted_games(games, team_stats, advanced)
    by_side = {(entry["game_code"], "local" if entry["home"] else "road"): entry
               for entry in entries}
    scope_entries = defaultdict(list)
    for entry in entries:
        for scope in _scopes(entry["phase"]):
            scope_entries[scope].append(entry)
    appearances = defaultdict(lambda: defaultdict(list))   # scope -> player -> [(entry, row)]
    for row in player_stats:
        entry = by_side.get((row["game_code"], row["side"]))
        seconds = row.get("seconds_played")
        if entry is None or seconds is None or seconds <= 0:
            continue
        for scope in _scopes(entry["phase"]):
            appearances[scope][row["person_key"]].append((entry, row))
    rows = []
    for scope in sorted(appearances):
        states = _league_states(scope_entries[scope])
        constants = {number: _constants(state) for number, state in states.items()}
        pending = []
        for person, played in appearances[scope].items():
            played.sort(key=lambda pair: (pair[0]["round"], pair[0]["game_code"]))
            state = {name: Decimal(0) for name in (*PLAYER, *CONTEXT)}
            games_played, latest, upcoming = 0, None, 0
            for number in (r for r in sorted(states) if r >= played[0][0]["round"]):
                while upcoming < len(played) and played[upcoming][0]["round"] <= number:
                    entry, row = played[upcoming]
                    values = {name: _num(row.get(name)) for name in PLAYER}
                    values.update(
                        team_assists=_num(entry["own"].get("assists")),
                        team_field_goals=_num(entry["own"].get("field_goals_made")),
                        team_possessions=_num(entry["possessions"]),
                        team_minutes=_num(entry["minutes"]))
                    for name, value in values.items():
                        state[name] = _add(state[name], value)
                    games_played += 1
                    latest, upcoming = row, upcoming + 1
                uper, aper = _uper(state, constants[number])
                pending.append({"scope": scope, "round_number": number, "person_key": person,
                                "club_code": latest.get("club_code"),
                                "player_name": latest.get("person_name"),
                                "games_played": games_played,
                                "seconds_played": state["seconds_played"],
                                "_uper": uper, "_aper": aper})
        weighted = defaultdict(lambda: [Decimal(0), Decimal(0)])
        for row in pending:
            if row["_aper"] is not None:
                total = weighted[row["round_number"]]
                total[0] += row["_aper"] * row["seconds_played"]
                total[1] += row["seconds_played"]
        for row in pending:
            total, seconds = weighted.get(row["round_number"], (Decimal(0), Decimal(0)))
            league_average = _div(total, seconds)
            uper, aper = row.pop("_uper"), row.pop("_aper")
            per = None
            if aper is not None and league_average:
                per = aper * AVERAGE / league_average
            for name, value in (("uper", uper), ("aper", aper), ("per", per)):
                row[name] = None if value is None else value.quantize(PLACES)
            rows.append(row)
    rows.sort(key=lambda r: (r["scope"], r["round_number"], r["person_key"]))
    return rows


def read_rows(cursor, competition_code, season_code):
    cursor.execute("SELECT * FROM silver.game_player_stats WHERE competition_code = %s "
                   "AND season_code = %s", (competition_code, season_code))
    players = _dict_rows(cursor)
    return derive_rows(*read_tables(cursor, competition_code, season_code), players)
