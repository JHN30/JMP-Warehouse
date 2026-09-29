"""Counted possessions per team and game (feature 19a), derived from play-by-play.

`derive_rows` is pure. `read_rows` and `replace_season` talk to the `silver` schema, one
season at a time; nothing reads Gold or Neon. The counted values sit next to the box-score
estimate from `game_team_advanced` and never replace it.
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
from shared import COMPETITION_CODES as PREFIX, DEFAULT_CONFIG, connect, elapsed

PLACES = Decimal("0.000001")
SOURCE_TABLES = ("games", "game_team_advanced", "play_by_play")
# A Silver load of either loaded table triggers a rebuild after the advanced stats.
TRIGGER_TABLES = ("games", "play_by_play")
PERIOD_RANK = {"FirstQuarter": 1, "SecondQuarter": 2, "ThirdQuarter": 3, "ForthQuarter": 4,
               "ExtraTime": 5}
QUARTER_SECONDS, OVERTIME_SECONDS = 600, 300
# E2008-E2014 also record many shots as layups and dunks, and blocked shots as `2FGAB`/`3FGAB`;
# with these types the event totals equal the box score's field goals made and attempted.
MADE = {"2FGM", "3FGM", "LAYUPMD", "DUNK"}
MISSED = {"2FGA", "3FGA", "LAYUPATT", "2FGAB", "3FGAB"}
FREE_THROWS = {"FTM", "FTA"}
PLAYS = MADE | MISSED | FREE_THROWS | {"TO", "O", "D"}
TECHNICAL = {"CMT", "CMTI", "C", "B"}


def _overtime(event):
    minute = event.get("minute")
    return 1 if minute is None or minute <= 40 else (minute - 41) // 5 + 1


def _game_end(events):
    """Elapsed seconds at the end of a game. Overtimes are counted from events that carry a
    clock: the trailing end-of-game events (`EG`, `EP`) have none and sit one minute past the
    last overtime."""
    overtimes = max((_overtime(e) for e in events
                     if PERIOD_RANK.get(e["period"]) == 5 and e.get("marker_time")),
                    default=0)
    return 4 * QUARTER_SECONDS + overtimes * OVERTIME_SECONDS


def _sort_key(event):
    period = PERIOD_RANK.get(event["period"], 9)
    return (period, _overtime(event) if period == 5 else 0, event["event_ordinal"])


def _period_bounds(event):
    """(elapsed seconds at the period start, period length) of an event's period."""
    rank = PERIOD_RANK.get(event["period"])
    if rank is None:
        return None
    if rank < 5:
        return (rank - 1) * QUARTER_SECONDS, QUARTER_SECONDS
    return 4 * QUARTER_SECONDS + (_overtime(event) - 1) * OVERTIME_SECONDS, OVERTIME_SECONDS


def _clock(event):
    """Elapsed game seconds of an event from its `MM:SS` time left, or None."""
    bounds, marker = _period_bounds(event), event.get("marker_time")
    if bounds is None or not marker:
        return None
    try:
        minutes, seconds = marker.split(":")
        left = int(minutes) * 60 + int(seconds)
    except ValueError:
        return None
    start, length = bounds
    return start + length - left if 0 <= left <= length else None


def _count(events, clubs):
    """Possessions and measured lengths per club for one game's ordered events."""
    result = {club: {"count": 0, "seconds": Decimal(0), "measured": 0} for club in clubs}
    plays = [e for e in events if e["play_type"] in PLAYS or e["play_type"] in TECHNICAL]
    state = {"owner": None, "start": None, "closed_by": None, "technical": False}

    def end(club, at):
        if club not in result:
            return
        entry = result[club]
        entry["count"] += 1
        if at is not None and state["start"] is not None and at >= state["start"]:
            entry["seconds"] += Decimal(at - state["start"])
            entry["measured"] += 1

    def next_play(index):
        for later in plays[index + 1:]:
            if later["play_type"] in PLAYS:
                return later
        return None

    period, period_end = None, None
    for index, event in enumerate(plays):
        kind, club, at = event["play_type"], event.get("club_code"), _clock(event)
        if event["period"] != period:
            if period is not None and state["owner"] is not None:
                end(state["owner"], period_end)
            period = event["period"]
            bounds = _period_bounds(event)
            period_end = None if bounds is None else bounds[0] + bounds[1]
            state.update(owner=None, closed_by=None, technical=False,
                         start=None if bounds is None else bounds[0])
        if kind in TECHNICAL:
            state["technical"] = True
            continue
        if club not in result:
            continue
        if kind in FREE_THROWS:
            following = next_play(index)
            final = not (following and following["play_type"] in FREE_THROWS
                         and following.get("club_code") == club
                         and following.get("marker_time") == event.get("marker_time"))
            if state["technical"]:
                state["technical"] = not final
                continue
            if state["closed_by"] == club:
                if at is not None:
                    state["start"] = at
                continue
            if state["owner"] != club:
                _take(state, result, club, at, end)
            if final and kind == "FTM":
                end(club, at)
                state.update(owner=None, start=at if at is not None else state["start"])
            continue
        state["technical"] = False
        if kind in MADE or kind in MISSED or kind == "TO" or kind == "O":
            if state["owner"] != club:
                _take(state, result, club, at, end)
            state["closed_by"] = None
            if kind in MADE:
                end(club, at)
                state.update(owner=None, closed_by=club,
                             start=at if at is not None else state["start"])
            elif kind == "TO":
                end(club, at)
                state.update(owner=None, start=at if at is not None else state["start"])
        elif kind == "D":
            if state["owner"] is not None and state["owner"] != club:
                end(state["owner"], at)
            state.update(owner=club, start=at if at is not None else state["start"],
                         closed_by=None)
    if period is not None and state["owner"] is not None:
        end(state["owner"], period_end)
    return result


def _take(state, result, club, at, end):
    """`club` acts while another club is recorded as holding the ball: an unrecorded change."""
    if state["owner"] is not None:
        end(state["owner"], at)
        state["start"] = at if at is not None else state["start"]
    state["owner"] = club


def _ratio(numerator, denominator):
    return None if not denominator else (numerator / denominator).quantize(PLACES)


def derive_rows(games, team_advanced, events):
    """Rows for `game_team_possessions`, sorted by game and side."""
    advanced = {(row["game_code"], row["side"]): row for row in team_advanced}
    by_game = {}
    for event in events:
        by_game.setdefault(event["game_code"], []).append(event)
    rows = []
    for game in sorted(games, key=lambda row: row["game_code"]):
        code = game["game_code"]
        if game.get("played") is not True or code not in by_game:
            continue
        sides = {"local": game.get("local_club_code"), "road": game.get("road_club_code")}
        if not all(sides.values()) or any((code, side) not in advanced for side in sides):
            continue
        counted = _count(sorted(by_game[code], key=_sort_key), set(sides.values()))
        for side, other in (("local", "road"), ("road", "local")):
            club = sides[side]
            entry = counted[club]
            estimate = advanced[(code, side)].get("possessions")
            rows.append({
                "game_code": code, "side": side, "club_code": club,
                "opponent_club_code": sides[other], "counted_possessions": entry["count"],
                "possession_seconds": entry["seconds"].quantize(PLACES),
                "avg_possession_seconds": _ratio(entry["seconds"], entry["measured"]),
                "estimated_possessions": estimate})
    return rows


def _dict_rows(cursor):
    names = [column[0] for column in cursor.description]
    return [dict(zip(names, values)) for values in cursor.fetchall()]


def read_rows(cursor, competition_code, season_code):
    scope = (competition_code, season_code)
    data = []
    for table in SOURCE_TABLES:
        cursor.execute(f'SELECT * FROM "{table}" WHERE competition_code = %s '
                       'AND season_code = %s', scope)
        data.append(_dict_rows(cursor))
    return derive_rows(*data)


TABLE = "game_team_possessions"


def replace_season(connection, competition_code, season_code, rows, name=TABLE):
    """DDL, delete, insert and the load-log entry commit together or not at all."""
    from psycopg2.extras import Json, execute_values

    loaded_at = datetime.now(timezone.utc)
    with connection:
        with connection.cursor() as cursor:
            cursor.execute(create_load_log_sql())
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


def stored_rows(cursor, name, competition_code, season_code):
    """The stored season slice of a derived table, without scope or provenance columns."""
    fields = [field.name for field in ADVANCED_TABLES[name].fields
              if field.name not in ("competition_code", "season_code")]
    columns = ", ".join(f'"{field}"' for field in fields)
    cursor.execute(f'SELECT {columns} FROM "{name}" '
                   'WHERE competition_code = %s AND season_code = %s',
                   (competition_code, season_code))
    return _dict_rows(cursor)


def differences_from_derivation(name, actual, expected, columns=("game_code", "side")):
    """ERROR issues where stored rows differ from a fresh derivation."""
    key = lambda row: tuple(row[column] for column in columns)
    stored = {key(row): row for row in actual}
    fresh = {key(row): row for row in expected}
    if stored.keys() != fresh.keys():
        return [("ERROR", "keys_differ_from_derivation", name,
                 len(stored.keys() ^ fresh.keys()))]
    differing = sum(stored[k] != fresh[k] for k in fresh)
    return [("ERROR", "values_differ_from_derivation", name, differing)] if differing else []


# A game whose counted possessions differ from the box-score estimate by more than this
# share is reported as a warning (see the data dictionary for the observed distribution).
TOLERANCE = Decimal("0.10")


def check_season(connection, competition_code, season_code):
    """Read-only checks; returns (severity, code, table, count) for each failure."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass(%s)", (TABLE,))
        if cursor.fetchone()[0] is None:
            return [("ERROR", "missing_table", TABLE, 1)]
        expected = read_rows(cursor, competition_code, season_code)
        actual = stored_rows(cursor, TABLE, competition_code, season_code)
    issues = differences_from_derivation(TABLE, actual, expected)
    far = sum(1 for row in actual
              if row["estimated_possessions"] and abs(
                  row["counted_possessions"] - row["estimated_possessions"])
              > TOLERANCE * row["estimated_possessions"])
    if far:
        issues.append(("WARN", "counted_far_from_estimate", TABLE, far))
    return issues


def run_seasons(config_path, competition, season_codes, dry_run=False, quality_only=False,
                read=None, replace=None, check=None):
    """Derive and store every season; returns True when no ERROR was found.

    `read`, `replace` and `check` default to this module's functions, looked up at call time;
    the other play-by-play tables pass their own."""
    read, replace, check = (read or read_rows, replace or replace_season,
                            check or check_season)
    code = PREFIX[competition]
    started = time.monotonic()
    passed = True
    connection = connect(config_path)
    try:
        for season_code in season_codes:
            if not quality_only:
                with connection.cursor() as cursor:
                    rows = read(cursor, code, season_code)
                connection.rollback()
                if dry_run:
                    print(f"  {season_code}: {len(rows):,} rows (dry run; "
                          "database unchanged)", flush=True)
                    continue
                replace(connection, code, season_code, rows)
                print(f"  {season_code}: {len(rows):,} rows | elapsed "
                      f"{elapsed(started)}", flush=True)
            if dry_run:
                continue
            issues = check(connection, code, season_code)
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


def main(argv=None, run=None,
         description="Count possessions per team and game in silver from play-by-play."):
    from main import available_seasons, requested_seasons, DEFAULT_DATA_ROOT

    parser = argparse.ArgumentParser(description=description)
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
        passed = (run or run_seasons)(args.config, args.competition, seasons,
                                      args.dry_run, args.quality_only)
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Play-by-play derivation failed: {error}", file=sys.stderr, flush=True)
        return 1
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
