"""Home/away splits and last-N game windows after every round, per scope.

Rows match `team_round_stats` (same scopes, rounds and clubs). Each group sums a
subset of the club's counted games through the round: home (the `local` side),
away (`road`), and its most recent 5 and 10 games.
"""

from collections import defaultdict
from decimal import Decimal

from gold_etl.schema import SPLIT_GROUPS, SPLIT_MEASURES, WINDOWS
from gold_etl.team_rounds import _counted_games, _scopes, read_tables

PLACES = Decimal("0.000001")


def _ratio(numerator, denominator):
    return (Decimal(numerator) / Decimal(denominator)).quantize(PLACES)


def _group(entries):
    """Games, wins and rate measures for one subset of games (NULL rates without data)."""
    result = {"games": len(entries), "wins": sum(entry["won"] is True for entry in entries)}
    result.update({name: None for name in SPLIT_MEASURES})
    if not entries:
        return result
    values = [(entry["own"].get("points"), entry["opp"].get("points"),
               entry["possessions"], entry["minutes"]) for entry in entries]
    if any(value is None for row in values for value in row):
        return result
    points = sum(Decimal(str(row[0])) for row in values)
    against = sum(Decimal(str(row[1])) for row in values)
    possessions = sum(Decimal(str(row[2])) for row in values)
    minutes = sum(Decimal(str(row[3])) for row in values)
    result["mov"] = _ratio(points - against, len(entries))
    if possessions and minutes:
        result["offensive_rating"] = _ratio(100 * points, possessions)
        result["defensive_rating"] = _ratio(100 * against, possessions)
        result["net_rating"] = _ratio(100 * (points - against), possessions)
        result["pace"] = _ratio(40 * possessions, minutes)
    return result


def derive_rows(games, team_stats, advanced, clubs=()):
    """Rows for `team_round_splits`, sorted by scope, round and club."""
    by_scope = defaultdict(lambda: defaultdict(list))
    for entry in _counted_games(games, team_stats, advanced):
        for scope in _scopes(entry["phase"]):
            by_scope[scope][entry["club"]].append(entry)
    rows = []
    for scope in sorted(by_scope):
        clubs_in_scope = by_scope[scope]
        rounds = sorted({entry["round"] for played in clubs_in_scope.values()
                         for entry in played})
        for club, played in sorted(clubs_in_scope.items()):
            played.sort(key=lambda entry: (entry["round"], entry["game_code"]))
            through = []
            pending = iter(played)
            upcoming = next(pending, None)
            for number in (r for r in rounds if r >= played[0]["round"]):
                while upcoming is not None and upcoming["round"] <= number:
                    through.append(upcoming)
                    upcoming = next(pending, None)
                subsets = {"home": [e for e in through if e["home"]],
                           "away": [e for e in through if not e["home"]],
                           **{f"last{size}": through[-size:] for size in WINDOWS}}
                row = {"scope": scope, "round_number": number, "club_code": club}
                for group in SPLIT_GROUPS:
                    for name, value in _group(subsets[group]).items():
                        row[f"{group}_{name}"] = value
                rows.append(row)
    rows.sort(key=lambda row: (row["scope"], row["round_number"], row["club_code"]))
    return rows


def read_rows(cursor, competition_code, season_code):
    return derive_rows(*read_tables(cursor, competition_code, season_code))
