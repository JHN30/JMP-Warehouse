"""Score flow per team and game (feature 19b), derived from the running score in play-by-play.

`derive_rows` is pure. It reuses feature 19a's event ordering and game clock, and shares its
storage and season runner. Nothing reads Gold or Neon.
"""

import sys
from decimal import Decimal

from possessions import (_clock, _dict_rows, _game_end, _sort_key, events_by_game,
                         differences_from_derivation, main as _main, replace_season as _replace,
                         run_seasons as _run, stored_rows)

TABLE = "game_team_score_flow"
SOURCE_TABLES = ("games", "play_by_play")
TRIGGER_TABLES = ("games", "play_by_play")
RUN_MINIMUM = 6
CLUTCH_MARGIN = 5
CLUTCH_START = 2100


def _walk(events):
    """Score flow of one game's ordered events, or None when no event carries a score."""
    a = b = 0
    previous, last_leader = 0, None
    seconds = {"a": 0, "b": 0, "tied": 0, "clutch": 0}
    counts = {"changes": 0, "ties": 0}
    largest = {"a": 0, "b": 0}
    runs = {"a": [], "b": []}
    current = {"team": None, "points": 0}
    clutch = {"a": 0, "b": 0}
    clock_ok, scored = True, False

    def interval(margin, start, end):
        span = max(0, end - start)
        seconds["a" if margin > 0 else "b" if margin < 0 else "tied"] += span
        if abs(margin) <= CLUTCH_MARGIN:
            seconds["clutch"] += max(0, end - max(start, CLUTCH_START))

    def close_run():
        if current["team"] is not None:
            runs[current["team"]].append(current["points"])
        current.update(team=None, points=0)

    for event in events:
        new_a = event.get("points_a") if event.get("points_a") is not None else a
        new_b = event.get("points_b") if event.get("points_b") is not None else b
        if event.get("points_a") is None and event.get("points_b") is None:
            continue
        scored = True
        if (new_a, new_b) == (a, b):
            continue
        at = _clock(event)
        if at is None:
            clock_ok, at = False, previous
        at = max(at, previous)
        margin = a - b
        interval(margin, previous, at)
        gained_a, gained_b = new_a - a, new_b - b
        if at >= CLUTCH_START and abs(margin) <= CLUTCH_MARGIN:
            clutch["a"] += max(0, gained_a)
            clutch["b"] += max(0, gained_b)
        if gained_a > 0 and gained_b <= 0 or gained_b > 0 and gained_a <= 0:
            team, points = ("a", gained_a) if gained_a > 0 else ("b", gained_b)
            if current["team"] != team:
                close_run()
                current["team"] = team
            current["points"] += points
        else:
            close_run()
        a, b, previous = new_a, new_b, at
        margin = a - b
        leader = "a" if margin > 0 else "b" if margin < 0 else None
        if leader:
            if last_leader and leader != last_leader:
                counts["changes"] += 1
            last_leader = leader
        elif a > 0:
            counts["ties"] += 1
        largest["a"], largest["b"] = max(largest["a"], margin), max(largest["b"], -margin)
    if not scored:
        return None
    interval(a - b, previous, _game_end(events))
    close_run()
    return {"points": {"a": a, "b": b}, "seconds": seconds, "counts": counts,
            "largest": largest, "runs": runs, "clutch": clutch, "clock_ok": clock_ok}


def derive_rows(games, events):
    """Rows for `game_team_score_flow`, sorted by game and side."""
    by_game = events_by_game(events)
    rows = []
    for game in sorted(games, key=lambda row: row["game_code"]):
        code = game["game_code"]
        if game.get("played") is not True or code not in by_game:
            continue
        sides = {"local": game.get("local_club_code"), "road": game.get("road_club_code")}
        if not all(sides.values()):
            continue
        flow = _walk(sorted(by_game[code], key=_sort_key))
        if flow is None:
            continue
        for side, other, own, opp in (("local", "road", "a", "b"), ("road", "local", "b", "a")):
            timed = flow["clock_ok"]
            rows.append({
                "game_code": code, "side": side, "club_code": sides[side],
                "opponent_club_code": sides[other],
                "points_for": flow["points"][own], "points_against": flow["points"][opp],
                "lead_changes": flow["counts"]["changes"], "ties": flow["counts"]["ties"],
                "time_leading_seconds": Decimal(flow["seconds"][own]) if timed else None,
                "time_trailing_seconds": Decimal(flow["seconds"][opp]) if timed else None,
                "time_tied_seconds": Decimal(flow["seconds"]["tied"]) if timed else None,
                "largest_lead": flow["largest"][own],
                "longest_run": max(flow["runs"][own], default=0),
                "runs_6_plus": sum(run >= RUN_MINIMUM for run in flow["runs"][own]),
                "clutch_seconds": Decimal(flow["seconds"]["clutch"]) if timed else None,
                "clutch_points_for": flow["clutch"][own],
                "clutch_points_against": flow["clutch"][opp]})
    return rows


def read_rows(cursor, competition_code, season_code):
    scope = (competition_code, season_code)
    data = []
    for table in SOURCE_TABLES:
        cursor.execute(f'SELECT * FROM "{table}" WHERE competition_code = %s '
                       'AND season_code = %s', scope)
        data.append(_dict_rows(cursor))
    return derive_rows(*data)


def replace_season(connection, competition_code, season_code, rows):
    return _replace(connection, competition_code, season_code, rows, name=TABLE)


WARNING_QUERY = (
    'SELECT count(*) FROM "game_team_score_flow" AS f JOIN "games" AS g '
    'ON g.competition_code = f.competition_code AND g.season_code = f.season_code '
    'AND g.game_code = f.game_code '
    'WHERE f.competition_code = %s AND f.season_code = %s AND ('
    "(f.side = 'local' AND (f.points_for IS DISTINCT FROM g.local_score "
    'OR f.points_against IS DISTINCT FROM g.road_score)) OR '
    "(f.side = 'road' AND (f.points_for IS DISTINCT FROM g.road_score "
    'OR f.points_against IS DISTINCT FROM g.local_score)))')


def check_season(connection, competition_code, season_code):
    """Read-only checks; returns (severity, code, table, count) for each failure."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass(%s)", (TABLE,))
        if cursor.fetchone()[0] is None:
            return [("ERROR", "missing_table", TABLE, 1)]
        expected = read_rows(cursor, competition_code, season_code)
        actual = stored_rows(cursor, TABLE, competition_code, season_code)
        issues = differences_from_derivation(TABLE, actual, expected)
        cursor.execute(WARNING_QUERY, (competition_code, season_code))
        differing = cursor.fetchone()[0]
    if differing:
        issues.append(("WARN", "final_score_differs_from_game", TABLE, differing))
    return issues


def run_seasons(config_path, competition, season_codes, dry_run=False, quality_only=False):
    return _run(config_path, competition, season_codes, dry_run, quality_only,
                read=read_rows, replace=replace_season, check=check_season)


def main(argv=None):
    return _main(argv, run=run_seasons,
                 description="Derive score flow per team and game in silver from play-by-play.")


if __name__ == "__main__":
    sys.exit(main())
