"""Per-team play-by-play aggregates per season scope (feature 19d).

Scopes are `all`, each phase, and `PS` (postseason phases together), as in the round tables.
The inputs are the per-game Silver tables of features 19a-19c; nothing reads Gold or Neon.
"""

from collections import defaultdict
from decimal import Decimal

from gold_etl.standings import _dict_rows
from gold_etl.team_rounds import _scopes

PLACES = Decimal("0.000001")
SOURCES = {"game_team_possessions": "possessions.py", "game_team_score_flow": "score_flow.py",
           "game_team_shot_splits": "shot_splits.py", "game_team_shot_zones": "shot_zones.py"}
SPLIT_POINTS = ("fast_break_points", "second_chance_points", "points_off_turnover_points")


def read_silver(cursor, competition_code, season_code, tables):
    """`silver.games` plus the named derived tables, each fully fetched before the next query."""
    scope = (competition_code, season_code)
    data = []
    for table in ("games", *tables):
        if table in SOURCES:
            cursor.execute("SELECT to_regclass(%s)", (f"silver.{table}",))
            if cursor.fetchone()[0] is None:
                raise ValueError(f"silver.{table} is missing; run "
                                 f"python postgres_etl/{SOURCES[table]} -sc <seasons> first")
        cursor.execute(f"SELECT * FROM silver.{table} WHERE competition_code = %s "
                       "AND season_code = %s", scope)
        data.append(_dict_rows(cursor))
    return data


def _total(values):
    values = [Decimal(str(value)) for value in values if value is not None]
    return sum(values, Decimal(0)) if values else None


def _mean(values):
    values = [Decimal(str(value)) for value in values if value is not None]
    return (sum(values, Decimal(0)) / len(values)).quantize(PLACES) if values else None


def _ratio(numerator, denominator):
    if numerator is None or not denominator:
        return None
    return (Decimal(str(numerator)) / Decimal(str(denominator))).quantize(PLACES)


def _by_scope(games, rows):
    """Rows grouped by (scope, club) using the phase of each played game."""
    phases = {game["game_code"]: game["phase_code"] for game in games
              if game.get("played") is True and game.get("phase_code")}
    grouped = defaultdict(list)
    for row in rows:
        phase = phases.get(row["game_code"])
        if phase is None or not row.get("club_code"):
            continue
        for scope in _scopes(phase):
            grouped[(scope, row["club_code"])].append(row)
    return grouped


def derive_rows(games, possessions, flow, splits):
    """Rows for `team_pbp_stats`, sorted by scope and club."""
    tables = {name: _by_scope(games, rows) for name, rows in
              (("possessions", possessions), ("flow", flow), ("splits", splits))}
    rows = []
    for scope, club in sorted(set().union(*(set(grouped) for grouped in tables.values()))):
        p = tables["possessions"].get((scope, club), [])
        f = tables["flow"].get((scope, club), [])
        s = tables["splits"].get((scope, club), [])
        measured = [row for row in p if row["avg_possession_seconds"] is not None
                    and row["counted_possessions"]]
        weight = sum(row["counted_possessions"] for row in measured)
        timed = [row for row in f if row["time_leading_seconds"] is not None]
        flagged = [row for row in s if row["fast_break_points"] is not None]
        made = _total(row["field_goals_made"] for row in s)
        assisted = _total(row["assisted_field_goals"] for row in s)
        row = {
            "scope": scope, "club_code": club, "games": len(p),
            "counted_possessions": _total(r["counted_possessions"] for r in p),
            "estimated_possessions": _total(r["estimated_possessions"] for r in p),
            "possession_seconds": _total(r["possession_seconds"] for r in p),
            "avg_possession_seconds": _ratio(_total(
                Decimal(str(r["avg_possession_seconds"])) * r["counted_possessions"]
                for r in measured), weight),
            "lead_changes_per_game": _mean(r["lead_changes"] for r in f),
            "ties_per_game": _mean(r["ties"] for r in f),
            "timed_games": len(timed),
            "time_leading_seconds": _total(r["time_leading_seconds"] for r in timed),
            "time_trailing_seconds": _total(r["time_trailing_seconds"] for r in timed),
            "time_tied_seconds": _total(r["time_tied_seconds"] for r in timed),
            "largest_lead": max((r["largest_lead"] for r in f), default=None),
            "longest_run": max((r["longest_run"] for r in f), default=None),
            "runs_6_plus": _total(r["runs_6_plus"] for r in f),
            "clutch_games": sum(1 for r in timed if r["clutch_seconds"] > 0),
            "clutch_seconds": _total(r["clutch_seconds"] for r in timed),
            "clutch_points_for": _total(r["clutch_points_for"] for r in f),
            "clutch_points_against": _total(r["clutch_points_against"] for r in f),
            "flagged_games": len(flagged),
            "field_goals_made": made, "assisted_field_goals": assisted,
            "assisted_fg_pct": _ratio(assisted, made),
        }
        for column in SPLIT_POINTS:
            row[column] = _total(r[column] for r in flagged)
        rows.append(row)
    return rows


def read_rows(cursor, competition_code, season_code):
    return derive_rows(*read_silver(cursor, competition_code, season_code, (
        "game_team_possessions", "game_team_score_flow", "game_team_shot_splits")))
