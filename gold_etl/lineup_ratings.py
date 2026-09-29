"""2-man, 3-man and 5-man lineup ratings per club and scope (feature 29c).

Every stored lineup stint of feature 29b holds ten pairs, ten triples and one five of the club's
players; each group's stints are summed per scope (`all`, each phase, `PS`). Ratings are points
per 100 possessions from the counted possessions of feature 19a. Small samples are kept, with
their possessions, for the consumer to filter. Nothing reads Gold or Neon.
"""

from collections import defaultdict
from itertools import combinations

from gold_etl.player_on_off import MEASURES, _minus, _rating, _stint_values
from gold_etl.team_pbp import read_silver
from gold_etl.team_rounds import _scopes

SIZES = (2, 3, 5)


def derive_rows(games, stints, players):
    """Rows for `lineup_ratings`, sorted by scope, club, size and lineup."""
    phases = {game["game_code"]: game["phase_code"] for game in games
              if game.get("played") is True and game.get("phase_code")}
    names = {}
    for player in players:
        if player.get("person_name") and player["person_key"] not in names:
            names[player["person_key"]] = player["person_name"]
    totals = defaultdict(lambda: [0] * len(MEASURES))
    played = defaultdict(set)
    for row in stints:
        phase = phases.get(row["game_code"])
        if phase is None or not row.get("club_code"):
            continue
        values = _stint_values(row)
        members = row["players"].split(",")
        for scope in _scopes(phase):
            for size in SIZES:
                for group in combinations(members, size):
                    key = (scope, row["club_code"], size, ",".join(group))
                    for index, value in enumerate(values):
                        totals[key][index] += value
                    played[key].add(row["game_code"])
    rows = []
    for key, values in sorted(totals.items()):
        scope, club, size, lineup = key
        ortg, drtg = _rating(values[3], values[1]), _rating(values[4], values[2])
        rows.append({
            "scope": scope, "club_code": club, "lineup_size": size, "lineup": lineup,
            "lineup_names": "; ".join(names.get(person, person)
                                      for person in lineup.split(",")),
            "games": len(played[key]),
            **dict(zip(MEASURES, values)),
            "ortg": ortg, "drtg": drtg, "net_rating": _minus(ortg, drtg)})
    return rows


def read_rows(cursor, competition_code, season_code):
    return derive_rows(*read_silver(cursor, competition_code, season_code,
                                    ("game_team_lineup_stints", "game_player_stats")))
