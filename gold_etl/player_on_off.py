"""Player on/off ratings per season scope (feature 29b).

For every player, club and scope (`all`, each phase, `PS`) the stints with the player on court
are summed against the club's other complete stints in the same scope. Ratings are points per
100 possessions from the counted possessions of feature 19a. The inputs are the Silver tables
`game_team_lineup_stints` and `game_player_stats`; nothing reads Gold or Neon.
"""

from collections import defaultdict
from decimal import Decimal

from gold_etl.team_pbp import PLACES, read_silver
from gold_etl.team_rounds import _scopes

MEASURES = ("seconds", "possessions_for", "possessions_against", "points_for",
            "points_against")


def _rating(points, possessions):
    if not possessions:
        return None
    return (Decimal(100) * points / possessions).quantize(PLACES)


def _minus(first, second):
    return None if first is None or second is None else first - second


def _stint_values(row):
    return (row["end_seconds"] - row["start_seconds"], row["possessions_for"],
            row["possessions_against"], row["points_for"], row["points_against"])


def derive_rows(games, stints, players):
    """Rows for `player_on_off`, sorted by scope, club and player."""
    phases = {game["game_code"]: game["phase_code"] for game in games
              if game.get("played") is True and game.get("phase_code")}
    names = {}
    for player in players:
        if player.get("person_name") and player["person_key"] not in names:
            names[player["person_key"]] = player["person_name"]
    team = defaultdict(lambda: [0] * len(MEASURES))
    on = defaultdict(lambda: [0] * len(MEASURES))
    played = defaultdict(set)
    for row in stints:
        phase = phases.get(row["game_code"])
        if phase is None or not row.get("club_code"):
            continue
        values = _stint_values(row)
        for scope in _scopes(phase):
            for index, value in enumerate(values):
                team[(scope, row["club_code"])][index] += value
            for person in row["players"].split(","):
                key = (scope, row["club_code"], person)
                for index, value in enumerate(values):
                    on[key][index] += value
                played[key].add(row["game_code"])
    rows = []
    for key, own in sorted(on.items()):
        scope, club, person = key
        off = [total - part for total, part in zip(team[(scope, club)], own)]
        row = {"scope": scope, "club_code": club, "person_key": person,
               "player_name": names.get(person), "games": len(played[key])}
        for state, values in (("on", own), ("off", off)):
            row.update({f"{state}_{name}": value for name, value in zip(MEASURES, values)})
        for state, values in (("on", own), ("off", off)):
            row[f"{state}_ortg"] = _rating(values[3], values[1])
            row[f"{state}_drtg"] = _rating(values[4], values[2])
            row[f"{state}_net_rating"] = _minus(row[f"{state}_ortg"], row[f"{state}_drtg"])
        row["ortg_diff"] = _minus(row["on_ortg"], row["off_ortg"])
        row["drtg_diff"] = _minus(row["on_drtg"], row["off_drtg"])
        row["net_rating_diff"] = _minus(row["on_net_rating"], row["off_net_rating"])
        rows.append(row)
    return rows


def read_rows(cursor, competition_code, season_code):
    return derive_rows(*read_silver(cursor, competition_code, season_code,
                                    ("game_team_lineup_stints", "game_player_stats")))
