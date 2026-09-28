"""Page-shaped per-round team advanced stats: a projection of the three team round tables.

One row per scope, round and club, taken from `team_round_stats`, `team_round_ratings` and
`team_round_splits`. The three derivations run in memory on the same Silver read, so the
table never depends on Gold build order, and no value is recomputed here.
"""

from gold_etl.schema import STANDINGS_STATS_SOURCES
from gold_etl.team_ratings import derive_rows as rating_rows
from gold_etl.team_rounds import derive_rows as stats_rows, read_tables
from gold_etl.team_splits import derive_rows as split_rows

DERIVATIONS = {"team_round_stats": stats_rows, "team_round_ratings": rating_rows,
               "team_round_splits": split_rows}
KEY = ("scope", "round_number", "club_code")


def derive_rows(games, team_stats, advanced, clubs):
    """Rows for `app_standings_stats`, sorted by scope, round and club."""
    merged = {}
    for name, _, columns in STANDINGS_STATS_SOURCES:
        for row in DERIVATIONS[name](games, team_stats, advanced, clubs):
            key = tuple(row[column] for column in KEY)
            if name == STANDINGS_STATS_SOURCES[0][0]:
                merged[key] = dict(zip(KEY, key))
            elif key not in merged:
                raise ValueError(f"{name} has a row with no team_round_stats row: {key}")
            for column in columns:
                merged[key][column] = row[column]
    for key, row in merged.items():
        missing = [column for _, _, columns in STANDINGS_STATS_SOURCES
                   for column in columns if column not in row]
        if missing:
            raise ValueError(f"no {missing[0]} value for {key}")
    return [merged[key] for key in sorted(merged)]


def read_rows(cursor, competition_code, season_code):
    return derive_rows(*read_tables(cursor, competition_code, season_code))
