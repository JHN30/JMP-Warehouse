"""Shot-based splits per team and game (feature 19c): fast-break, second-chance and
off-turnover points from the shots feed, and assisted field goals from play-by-play.

`derive_rows` is pure. It shares 19a's storage and season runner; nothing reads Gold or Neon.
"""

import sys
from decimal import Decimal

from possessions import (MADE, _dict_rows, differences_from_derivation, main as _main,
                         replace_season as _replace, run_seasons as _run, stored_rows)

TABLE = "game_team_shot_splits"
SOURCE_TABLES = ("games", "shots", "play_by_play")
TRIGGER_TABLES = ("games", "play_by_play", "shots")
FLAGS = (("fastbreak", "fast_break_points"), ("second_chance", "second_chance_points"),
         ("points_off_turnover", "points_off_turnover_points"))
PLACES = Decimal("0.000001")


def _assists(events, clubs):
    """Made field goals and assisted field goals per club for one game's events.

    An `AS` event is an assist for one made field goal, but it is often logged at a different
    clock time than the shot (sometimes much later), so it cannot be paired by time. The count
    of `AS` events equals the box score's assists in 99.5% of team games; it is capped at the
    made field goals."""
    made = {club: 0 for club in clubs}
    assists = {club: 0 for club in clubs}
    for event in events:
        club, kind = event.get("club_code"), event["play_type"]
        if club not in made:
            continue
        if kind in MADE:
            made[club] += 1
        elif kind == "AS":
            assists[club] += 1
    return made, {club: min(assists[club], made[club]) for club in clubs}


def _splits(shots, clubs):
    """Flagged points per club, or None when any shot of the game has a NULL flag."""
    if any(shot.get(flag) is None for shot in shots for flag, _ in FLAGS):
        return None
    totals = {club: {column: 0 for _, column in FLAGS} for club in clubs}
    for shot in shots:
        club, points = shot.get("club_code"), shot.get("points") or 0
        if club not in totals or points <= 0:
            continue
        for flag, column in FLAGS:
            if shot[flag]:
                totals[club][column] += points
    return totals


def derive_rows(games, shots, events):
    """Rows for `game_team_shot_splits`, sorted by game and side."""
    shots_by_game, events_by_game = {}, {}
    for shot in shots:
        shots_by_game.setdefault(shot["game_code"], []).append(shot)
    for event in events:
        events_by_game.setdefault(event["game_code"], []).append(event)
    rows = []
    for game in sorted(games, key=lambda row: row["game_code"]):
        code = game["game_code"]
        if game.get("played") is not True or code not in events_by_game:
            continue
        sides = {"local": game.get("local_club_code"), "road": game.get("road_club_code")}
        if not all(sides.values()):
            continue
        clubs = set(sides.values())
        made, assisted = _assists(events_by_game[code], clubs)
        splits = _splits(shots_by_game.get(code, []), clubs) if code in shots_by_game else None
        for side, other in (("local", "road"), ("road", "local")):
            club = sides[side]
            row = {"game_code": code, "side": side, "club_code": club,
                   "opponent_club_code": sides[other],
                   "field_goals_made": made[club], "assisted_field_goals": assisted[club],
                   "assisted_fg_pct": (Decimal(assisted[club]) / made[club]).quantize(PLACES)
                   if made[club] else None}
            for _, column in FLAGS:
                row[column] = None if splits is None else splits[club][column]
            rows.append(row)
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


ASSISTS_QUERY = ('SELECT count(*) FROM "game_team_shot_splits" '
                 'WHERE competition_code = %s AND season_code = %s '
                 'AND assisted_field_goals > field_goals_made')
POINTS_QUERY = (
    'SELECT count(*) FROM (SELECT game_code, club_code, sum(points) AS points FROM "shots" '
    'WHERE competition_code = %s AND season_code = %s GROUP BY game_code, club_code) AS s '
    'JOIN "games" AS g ON g.competition_code = %s AND g.season_code = %s '
    'AND g.game_code = s.game_code '
    'WHERE s.points IS DISTINCT FROM CASE WHEN s.club_code = g.local_club_code '
    'THEN g.local_score WHEN s.club_code = g.road_club_code THEN g.road_score END')


def check_season(connection, competition_code, season_code):
    """Read-only checks; returns (severity, code, table, count) for each failure."""
    scope = (competition_code, season_code)
    with connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass(%s)", (TABLE,))
        if cursor.fetchone()[0] is None:
            return [("ERROR", "missing_table", TABLE, 1)]
        expected = read_rows(cursor, *scope)
        actual = stored_rows(cursor, TABLE, *scope)
        issues = differences_from_derivation(TABLE, actual, expected)
        cursor.execute(ASSISTS_QUERY, scope)
        assists = cursor.fetchone()[0]
        cursor.execute(POINTS_QUERY, scope + scope)
        points = cursor.fetchone()[0]
    if assists:
        issues.append(("WARN", "assisted_exceeds_made", TABLE, assists))
    if points:
        issues.append(("WARN", "shot_points_differ_from_game", TABLE, points))
    return issues


def run_seasons(config_path, competition, season_codes, dry_run=False, quality_only=False):
    return _run(config_path, competition, season_codes, dry_run, quality_only,
                read=read_rows, replace=replace_season, check=check_season)


def main(argv=None):
    return _main(argv, run=run_seasons, description=(
        "Derive shot-based splits per team and game in silver from shots and play-by-play."))


if __name__ == "__main__":
    sys.exit(main())
