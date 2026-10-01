"""Per-game advanced rows: Silver's box-score estimates plus single-game PER.

`game_team_advanced` and `game_player_advanced` project the feature 25 Silver tables to the
published column set. Game PER reuses the round-table functions: league constants are
cumulative over the game's phase scope through the game's round, the player's line and team
context are that one game, and `game_per` is scaled so the seconds-weighted mean `game_aper`
of the scope's round is 15.
"""

from collections import defaultdict
from decimal import Decimal

from gold_etl.player_ratings import (AVERAGE, CONTEXT, PLACES, PLAYER, _constants, _div,
                                     _league_states, _uper)
from gold_etl.player_rounds import _num
from gold_etl.schema import GAME_PLAYER_MEASURES, GAME_TEAM_MEASURES
from gold_etl.standings import _dict_rows
from gold_etl.team_rounds import _counted_games, read_tables

TEAM_KEY = ("game_code", "side", "club_code")
PLAYER_KEY = ("game_code", "side", "person_key", "club_code", "seconds_played")
PER_COLUMNS = ("game_uper", "game_aper", "game_per")


def team_rows(advanced):
    """Rows for `game_team_advanced`, sorted by game and side."""
    rows = [{name: row.get(name) for name in (*TEAM_KEY, *GAME_TEAM_MEASURES)}
            for row in advanced]
    rows.sort(key=lambda row: (row["game_code"], row["side"]))
    return rows


def _unadjusted(games, team_stats, advanced, player_stats):
    """{(game_code, side, person_key): (scope, round, uper, aper)} for played lines."""
    entries = _counted_games(games, team_stats, advanced)
    by_side = {(entry["game_code"], "local" if entry["home"] else "road"): entry
               for entry in entries}
    scope_entries = defaultdict(list)
    for entry in entries:
        scope_entries[entry["phase"]].append(entry)
    constants = {scope: {number: _constants(state)
                         for number, state in _league_states(rows).items()}
                 for scope, rows in scope_entries.items()}
    result = {}
    for row in player_stats:
        entry = by_side.get((row["game_code"], row["side"]))
        seconds = row.get("seconds_played")
        if entry is None or seconds is None or seconds <= 0:
            continue
        line = {name: _num(row.get(name)) for name in PLAYER}
        line.update(team_assists=_num(entry["own"].get("assists")),
                    team_field_goals=_num(entry["own"].get("field_goals_made")),
                    team_possessions=_num(entry["possessions"]),
                    team_minutes=_num(entry["minutes"]))
        uper, aper = _uper(line, constants[entry["phase"]][entry["round"]])
        result[(row["game_code"], row["side"], row["person_key"])] = (
            entry["phase"], entry["round"], uper, aper, line["seconds_played"])
    return result


def player_rows(games, team_stats, advanced, player_stats, player_advanced):
    """Rows for `game_player_advanced`, sorted by game, side and player."""
    ratings = _unadjusted(games, team_stats, advanced, player_stats)
    weighted = defaultdict(lambda: [Decimal(0), Decimal(0)])
    for scope, number, _, aper, seconds in ratings.values():
        if aper is not None:
            total = weighted[(scope, number)]
            total[0] += aper * seconds
            total[1] += seconds
    rows = []
    for source in player_advanced:
        row = {name: source.get(name) for name in (*PLAYER_KEY, *GAME_PLAYER_MEASURES)
               if name not in PER_COLUMNS}
        found = ratings.get((source["game_code"], source["side"], source["person_key"]))
        uper = aper = per = None
        if found is not None:
            scope, number, uper, aper, _ = found
            average = _div(*weighted[(scope, number)])
            if aper is not None and average:
                per = aper * AVERAGE / average
        for name, value in zip(PER_COLUMNS, (uper, aper, per)):
            row[name] = None if value is None else value.quantize(PLACES)
        rows.append(row)
    rows.sort(key=lambda row: (row["game_code"], row["side"], row["person_key"]))
    return rows


def read_rows(cursor, competition_code, season_code, name):
    games, team_stats, advanced, _ = read_tables(cursor, competition_code, season_code)
    if name == "game_team_advanced":
        return team_rows(advanced)
    scope = (competition_code, season_code)
    inputs = []
    for table in ("game_player_stats", "game_player_advanced"):
        cursor.execute(f"SELECT * FROM silver.{table} WHERE competition_code = %s "
                       "AND season_code = %s", scope)
        inputs.append(_dict_rows(cursor))
    return player_rows(games, team_stats, advanced, *inputs)
