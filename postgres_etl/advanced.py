"""Per-game advanced stats (feature 25): box-score estimates derived from Silver.

Player usage, assist, rebound, steal and block % use the events counted while the player
was on court (feature 32) when the game has play-by-play, else the estimate with a
3-minute floor.

`derive_rows` is pure. `read_rows` and `replace_season` talk to the `silver`
schema, one season at a time; nothing reads Gold or Neon.
"""

import argparse
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from flat_schema import (ADVANCED_TABLES, add_column_sql, create_index_sql,
                         create_load_log_sql, create_table_sql)
from lineups import EVENT_COLUMNS
from on_court_rates import derive_counts
from shared import COMPETITION_CODES as PREFIX, DEFAULT_CONFIG, connect, elapsed

FT_WEIGHT = Decimal("0.44")
PLACES = Decimal("0.000001")
SOURCE_TABLES = ("games", "game_period_scores", "game_team_stats",
                 "game_player_stats", "game_stat_gaps", "play_by_play")
# Box-score estimates of the time-dependent rates are NULL below this many seconds.
ESTIMATE_FLOOR_SECONDS = 180
TIME_RATES = ("usage_pct", "assist_pct", "orb_pct", "drb_pct", "trb_pct", "steal_pct",
              "block_pct")


def _num(value):
    return None if value is None else Decimal(str(value))


def _sum(*values):
    return None if any(value is None for value in values) else sum(values, Decimal(0))


def _div(numerator, denominator):
    """A ratio, or None when an input is missing or the denominator is zero."""
    if numerator is None or denominator is None or denominator == 0:
        return None
    return (numerator / denominator).quantize(PLACES)


def _stats(row):
    """One box-score row as Decimals under the names the formulas use."""
    names = {"pts": "points", "fgm": "field_goals_made", "fga": "field_goals_attempted",
             "tpm": "three_pointers_made", "tpa": "three_pointers_attempted",
             "ftm": "free_throws_made", "fta": "free_throws_attempted",
             "oreb": "offensive_rebounds", "dreb": "defensive_rebounds",
             "reb": "total_rebounds", "ast": "assists", "stl": "steals",
             "tov": "turnovers", "blk": "blocks", "pf": "fouls_committed"}
    return {short: _num(row.get(column)) for short, column in names.items()}


def _own_possessions(s):
    if any(s[name] is None for name in ("fga", "fta", "oreb", "tov")):
        return None
    return s["fga"] + FT_WEIGHT * s["fta"] - s["oreb"] + s["tov"]


def _efg(s):
    if s["fgm"] is None or s["tpm"] is None:
        return None
    return _div(s["fgm"] + Decimal("0.5") * s["tpm"], s["fga"])


def _tov_pct(s):
    if any(s[name] is None for name in ("fga", "fta", "tov")):
        return None
    return _div(s["tov"], s["fga"] + FT_WEIGHT * s["fta"] + s["tov"])


def _true_shooting(s):
    if any(s[name] is None for name in ("pts", "fga", "fta")):
        return None
    return _div(s["pts"], 2 * (s["fga"] + FT_WEIGHT * s["fta"]))


def _game_minutes(periods):
    """40 minutes plus 5 per overtime period (periods above the fourth)."""
    overtimes = {row["period_number"] for row in periods if row["period_number"] > 4}
    return Decimal(40 + 5 * len(overtimes))


def _team_row(game, side, own, opp, own_est, opp_est, minutes, opp_side):
    possessions = None if own_est is None or opp_est is None else (own_est + opp_est) / 2
    offensive = _div(None if own["pts"] is None else 100 * own["pts"], possessions)
    defensive = _div(None if opp["pts"] is None else 100 * opp["pts"], possessions)
    return {
        "game_code": game["game_code"], "side": side,
        "club_code": game.get(f"{side}_club_code"),
        "opponent_club_code": game.get(f"{opp_side}_club_code"),
        "phase_code": game.get("phase_code"), "round_number": game.get("round_number"),
        "game_minutes": minutes,
        "possessions": None if possessions is None else possessions.quantize(PLACES),
        "own_possessions_estimate": None if own_est is None else own_est.quantize(PLACES),
        "pace": _div(None if possessions is None else 40 * possessions, minutes),
        "offensive_rating": offensive, "defensive_rating": defensive,
        "net_rating": None if offensive is None or defensive is None
        else offensive - defensive,
        "efg_pct": _efg(own), "tov_pct": _tov_pct(own),
        "orb_pct": _div(own["oreb"], _sum(own["oreb"], opp["dreb"])),
        "drb_pct": _div(own["dreb"], _sum(own["dreb"], opp["oreb"])),
        "ft_rate": _div(own["ftm"], own["fga"]),
        "opp_efg_pct": _efg(opp), "opp_tov_pct": _tov_pct(opp),
        "opp_ft_rate": _div(opp["ftm"], opp["fga"]),
        "true_shooting_pct": _true_shooting(own),
        "assist_ratio": _div(own["ast"], own["fgm"]),
    }


def _game_score(s):
    if any(value is None for value in s.values()):
        return None
    return (s["pts"] + Decimal("0.4") * s["fgm"] - Decimal("0.7") * s["fga"]
            - Decimal("0.4") * (s["fta"] - s["ftm"]) + Decimal("0.7") * s["oreb"]
            + Decimal("0.3") * s["dreb"] + s["stl"] + Decimal("0.7") * s["ast"]
            + Decimal("0.7") * s["blk"] - Decimal("0.4") * s["pf"] - s["tov"]).quantize(PLACES)


def _on_court_rates(counts):
    """The time-dependent rates from the events counted while the player was on court."""
    mine, team, opp = counts["own"], counts["team"], counts["opp"]

    def plays(s):
        return s["fga"] + FT_WEIGHT * s["fta"] + s["tov"]

    return {
        "usage_pct": _div(plays(mine), plays(team)),
        "assist_pct": _div(mine["ast"], team["fgm"] - mine["fgm"]),
        "orb_pct": _div(mine["oreb"], team["oreb"] + opp["dreb"]),
        "drb_pct": _div(mine["dreb"], team["dreb"] + opp["oreb"]),
        "trb_pct": _div(mine["oreb"] + mine["dreb"],
                        team["oreb"] + team["dreb"] + opp["oreb"] + opp["dreb"]),
        "steal_pct": _div(mine["stl"], counts["opp_possessions"]),
        "block_pct": _div(mine["blk"], opp["two_pa"]),
    }


def _player_row(game_code, side, row, own, opp, opp_possessions, game_seconds, counts=None):
    p = _stats(row)
    seconds = _num(row.get("seconds_played"))
    share = _div(seconds, game_seconds)  # None for zero or unknown minutes
    used = _sum(p["fga"], None if p["fta"] is None else FT_WEIGHT * p["fta"], p["tov"])
    team_used = _sum(own["fga"], None if own["fta"] is None else FT_WEIGHT * own["fta"],
                     own["tov"])

    def rate(numerator, denominator):
        if share is None or denominator is None:
            return None
        return _div(numerator, share * denominator)

    def rebound(kind, opposing):
        return rate(p[kind], _sum(own[kind], opp[opposing]))

    team_assisted = None if share is None or own["fgm"] is None else share * own["fgm"]
    two_attempts = _sum(opp["fga"], None if opp["tpa"] is None else -opp["tpa"])
    result = {
        "game_code": game_code, "side": side, "person_key": row["person_key"],
        "club_code": row.get("club_code"), "seconds_played": seconds,
        "game_score": _game_score(p),
        "true_shooting_pct": _true_shooting(p), "efg_pct": _efg(p),
        "usage_pct": rate(used, team_used),
        "assist_pct": _div(p["ast"], None if team_assisted is None or p["fgm"] is None
                           else team_assisted - p["fgm"]),
        "orb_pct": rebound("oreb", "dreb"), "drb_pct": rebound("dreb", "oreb"),
        "trb_pct": rate(p["reb"], _sum(own["reb"], opp["reb"])),
        "steal_pct": rate(p["stl"], opp_possessions),
        "block_pct": rate(p["blk"], two_attempts),
        "tov_pct": _tov_pct(p),
        "rate_source": "estimate" if counts is None else "on_court",
    }
    if counts is not None:
        rates = _on_court_rates(counts) if share else dict.fromkeys(TIME_RATES)
    elif seconds is None or seconds < ESTIMATE_FLOOR_SECONDS:
        rates = dict.fromkeys(TIME_RATES)
    else:
        rates = {}
    result.update(rates)
    return result


def derive_rows(games, periods, team_stats, player_stats, gaps, events=()):
    """Return (team rows, player rows) for the played games with a full box score."""
    on_court = derive_counts(games, player_stats, events)
    no_box_score = {row["game_code"] for row in gaps if row["stat_name"] == "*"}
    totals = {(row["game_code"], row["side"]): row for row in team_stats
              if row["stats_kind"] == "total"}
    period_rows = {}
    for row in periods:
        period_rows.setdefault(row["game_code"], []).append(row)
    players = {}
    for row in player_stats:
        players.setdefault((row["game_code"], row["side"]), []).append(row)
    team_rows, player_rows = [], []
    for game in sorted(games, key=lambda row: row["game_code"]):
        code = game["game_code"]
        local, road = totals.get((code, "local")), totals.get((code, "road"))
        if game.get("played") is not True or code in no_box_score or not (local and road):
            continue
        stats = {"local": _stats(local), "road": _stats(road)}
        estimates = {side: _own_possessions(stats[side]) for side in stats}
        minutes = _game_minutes(period_rows.get(code, []))
        for side, other in (("local", "road"), ("road", "local")):
            row = _team_row(game, side, stats[side], stats[other], estimates[side],
                            estimates[other], minutes, other)
            team_rows.append(row)
            for player in players.get((code, side), []):
                player_rows.append(_player_row(
                    code, side, player, stats[side], stats[other], row["possessions"],
                    minutes * 60, on_court.get((code, side, player["person_key"]))))
    return team_rows, player_rows


def _dict_rows(cursor):
    names = [column[0] for column in cursor.description]
    return [dict(zip(names, values)) for values in cursor.fetchall()]


def read_rows(cursor, competition_code, season_code):
    scope = (competition_code, season_code)
    data = []
    for table in SOURCE_TABLES[:-1]:
        cursor.execute(f'SELECT * FROM "{table}" WHERE competition_code = %s '
                       'AND season_code = %s', scope)
        data.append(_dict_rows(cursor))
    cursor.execute(f'SELECT {", ".join(EVENT_COLUMNS)} FROM "play_by_play" '
                   'WHERE competition_code = %s AND season_code = %s', scope)
    data.append(_dict_rows(cursor))
    return derive_rows(*data)


def replace_season(connection, competition_code, season_code, team_rows, player_rows):
    """DDL, delete, insert and load-log entries commit together or not at all."""
    from psycopg2.extras import Json, execute_values

    loaded_at = datetime.now(timezone.utc)
    with connection:
        with connection.cursor() as cursor:
            cursor.execute(create_load_log_sql())
            for name, rows in (("game_team_advanced", team_rows),
                               ("game_player_advanced", player_rows)):
                spec = ADVANCED_TABLES[name]
                cursor.execute(create_table_sql(name))
                for statement in add_column_sql(name):
                    cursor.execute(statement)
                for statement in create_index_sql(name):
                    cursor.execute(statement)
                cursor.execute(f'DELETE FROM "{name}" WHERE "competition_code" = %s '
                               'AND "season_code" = %s', (competition_code, season_code))
                load_id = str(uuid4())
                fields = [field.name for field in spec.fields]
                names = ", ".join(f'"{column}"' for column in fields + ["load_id", "loaded_at"])
                values = [tuple(competition_code if field == "competition_code"
                                else season_code if field == "season_code" else row[field]
                                for field in fields) + (load_id, loaded_at) for row in rows]
                if values:
                    execute_values(cursor, f'INSERT INTO "{name}" ({names}) VALUES %s',
                                   values, page_size=1000)
                cursor.execute(
                    'INSERT INTO "load_log" ("competition_code", "season_code", '
                    '"table_name", "load_id", "loaded_at", "row_count", '
                    '"bronze_versions") VALUES (%s, %s, %s, %s, %s, %s, %s)',
                    (competition_code, season_code, name, load_id, loaded_at,
                     len(values), Json({})))


SCOPED = ("competition_code = %s AND season_code = %s")
CHECKS = (
    ("ERROR", "missing_team_rows", "game_team_advanced", (
        'SELECT count(*) FROM "games" AS g WHERE g.competition_code = %s '
        'AND g.season_code = %s AND g.played IS TRUE AND NOT EXISTS ('
        'SELECT 1 FROM "game_stat_gaps" AS gap WHERE gap.competition_code = g.competition_code '
        "AND gap.season_code = g.season_code AND gap.game_code = g.game_code "
        "AND gap.stat_name = '*') AND (SELECT count(*) FROM \"game_team_stats\" AS t "
        'WHERE t.competition_code = g.competition_code AND t.season_code = g.season_code '
        "AND t.game_code = g.game_code AND t.stats_kind = 'total') = 2 AND ("
        'SELECT count(*) FROM "game_team_advanced" AS a WHERE a.competition_code = '
        'g.competition_code AND a.season_code = g.season_code '
        'AND a.game_code = g.game_code) < 2')),
    ("ERROR", "missing_player_rows", "game_player_advanced", (
        'SELECT count(*) FROM "game_player_stats" AS p JOIN "game_team_advanced" AS t '
        'ON t.competition_code = p.competition_code AND t.season_code = p.season_code '
        'AND t.game_code = p.game_code AND t.side = p.side '
        'LEFT JOIN "game_player_advanced" AS a ON a.competition_code = p.competition_code '
        'AND a.season_code = p.season_code AND a.game_code = p.game_code '
        'AND a.side = p.side AND a.person_key = p.person_key '
        'WHERE p.competition_code = %s AND p.season_code = %s AND a.person_key IS NULL')),
    ("ERROR", "possessions_differ_between_sides", "game_team_advanced", (
        'SELECT count(*) FROM (SELECT game_code FROM "game_team_advanced" '
        f'WHERE {SCOPED} GROUP BY game_code HAVING count(DISTINCT possessions) > 1 '
        'OR (count(*) = 2 AND count(possessions) = 1)) AS mismatched')),
    ("ERROR", "estimate_rate_below_floor", "game_player_advanced", (
        'SELECT count(*) FROM "game_player_advanced" '
        f"WHERE {SCOPED} AND rate_source = 'estimate' AND (seconds_played IS NULL "
        f"OR seconds_played < {ESTIMATE_FLOOR_SECONDS}) AND num_nonnulls("
        + ", ".join(TIME_RATES) + ") > 0")),
    ("WARN", "on_court_rate_out_of_range", "game_player_advanced", (
        'SELECT count(*) FROM "game_player_advanced" '
        f"WHERE {SCOPED} AND rate_source = 'on_court' AND ("
        + " OR ".join(f"{name} NOT BETWEEN 0 AND 1" for name in TIME_RATES) + ")")),
    ("WARN", "implausible_pace_or_rating", "game_team_advanced", (
        'SELECT count(*) FROM "game_team_advanced" '
        f'WHERE {SCOPED} AND (pace NOT BETWEEN 30 AND 150 '
        'OR offensive_rating NOT BETWEEN 20 AND 250)')),
)


def check_season(connection, competition_code, season_code):
    """Read-only checks; returns (severity, code, table, count) for each failure."""
    issues = []
    with connection.cursor() as cursor:
        for severity, code, table, query in CHECKS:
            cursor.execute("SELECT to_regclass(%s)", (table,))
            if cursor.fetchone()[0] is None:
                issues.append(("ERROR", "missing_table", table, 1))
                continue
            cursor.execute(query, (competition_code, season_code))
            count = cursor.fetchone()[0]
            if count:
                issues.append((severity, code, table, count))
    return issues


def run_seasons(config_path, competition, season_codes, dry_run=False, quality_only=False):
    """Derive and store every season; returns True when no ERROR was found."""
    code = PREFIX[competition]
    started = time.monotonic()
    passed = True
    connection = connect(config_path)
    try:
        for season_code in season_codes:
            if not quality_only:
                with connection.cursor() as cursor:
                    team_rows, player_rows = read_rows(cursor, code, season_code)
                connection.rollback()
                if dry_run:
                    print(f"  {season_code}: {len(team_rows):,} team rows, "
                          f"{len(player_rows):,} player rows (dry run; database unchanged)",
                          flush=True)
                    continue
                replace_season(connection, code, season_code, team_rows, player_rows)
                print(f"  {season_code}: {len(team_rows):,} team rows, "
                      f"{len(player_rows):,} player rows | elapsed {elapsed(started)}",
                      flush=True)
            if dry_run:
                continue
            issues = check_season(connection, code, season_code)
            connection.rollback()
            errors = [issue for issue in issues if issue[0] == "ERROR"]
            passed &= not errors
            print(f"  Quality {season_code}: {len(errors)} error(s), "
                  f"{len(issues) - len(errors)} warning(s)", flush=True)
            for severity, issue, table, count in issues:
                print(f"    {severity} {table}: {issue} ({count:,} row(s))", flush=True)
    finally:
        connection.close()
    return passed


def main(argv=None):
    from main import available_seasons, requested_seasons, DEFAULT_DATA_ROOT

    parser = argparse.ArgumentParser(
        description="Derive per-game advanced stats in silver from the loaded box scores.")
    parser.add_argument("-cp", "--competition", choices=PREFIX, default="euroleague")
    parser.add_argument("-sc", "--season-code", nargs="+", default=["latest"],
                        help="Years, codes, ranges, 'current', 'latest', or 'all' (as postgres_etl/main.py).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Derive and count rows without writing.")
    parser.add_argument("--quality-only", action="store_true",
                        help="Check stored rows without deriving or changing them.")
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args(argv)
    if args.dry_run and args.quality_only:
        parser.error("--dry-run cannot be combined with --quality-only")
    seasons = requested_seasons(args.season_code, args.competition,
                                available_seasons(args.data_root, args.competition), parser)
    try:
        passed = run_seasons(args.config, args.competition, seasons,
                             args.dry_run, args.quality_only)
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Advanced stats failed: {error}", file=sys.stderr, flush=True)
        return 1
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
