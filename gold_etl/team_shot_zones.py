"""Per-team shot zone aggregates per season scope (feature 19d).

Scopes are `all`, each phase, and `PS`, as in the round tables. The input is the per-game
`silver.game_team_shot_zones` table of feature 19c; nothing reads Gold or Neon.
"""

from collections import defaultdict

from gold_etl.team_pbp import _by_scope, _ratio, read_silver


def derive_rows(games, zones):
    """Rows for `team_shot_zone_stats`, sorted by scope, club and zone."""
    totals = defaultdict(lambda: {"attempts": 0, "made": 0, "points": 0})
    for (scope, club), rows in _by_scope(games, zones).items():
        for row in rows:
            entry = totals[(scope, club, row["zone"])]
            for column in ("attempts", "made", "points"):
                entry[column] += row[column] or 0
    attempts = defaultdict(int)
    for (scope, club, _), entry in totals.items():
        attempts[(scope, club)] += entry["attempts"]
    return [{"scope": scope, "club_code": club, "zone": zone, **entry,
             "fg_pct": _ratio(entry["made"], entry["attempts"]),
             "attempt_share": _ratio(entry["attempts"], attempts[(scope, club)])}
            for (scope, club, zone), entry in sorted(totals.items())]


def read_rows(cursor, competition_code, season_code):
    return derive_rows(*read_silver(cursor, competition_code, season_code,
                                    ("game_team_shot_zones",)))
