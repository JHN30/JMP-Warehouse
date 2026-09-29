"""On-court intervals per player and game (feature 29a), rebuilt from starters and substitutions.

`derive_rows` is pure. It reuses feature 19a's event ordering and game clock and shares its
storage and season runner. Nothing reads Gold or Neon.
"""

import sys

from possessions import (_clock, _dict_rows, _game_end, _period_bounds, _sort_key,
                         differences_from_derivation,
                         main as _main, replace_season as _replace, run_seasons as _run,
                         stored_rows)

TABLE = "game_player_on_court"
SOURCE_TABLES = ("games", "game_player_stats", "play_by_play")
TRIGGER_TABLES = SOURCE_TABLES
# Older box scores have minute precision, so smaller differences are not reported.
TOLERANCE_SECONDS = 120
EVENT_COLUMNS = ("game_code", "period", "event_ordinal", "club_code", "person_code",
                 "play_type", "minute", "marker_time")


def _at(event, previous):
    """Elapsed game seconds of a substitution. Older seasons log period-start substitutions
    at times outside the period (such as `11:00`); those, and missing clocks, use the period
    start. Time never runs backwards."""
    at = _clock(event)
    if at is None:
        bounds = _period_bounds(event)
        at = bounds[0] if bounds else previous
    return max(at, previous)


def _side_intervals(starters, events, club, end):
    """Intervals per person key for one side, in time order."""
    on = {person: 0 for person in starters}
    intervals = {}
    previous = 0

    def close(person, start, stop):
        if stop <= start:
            return
        spans = intervals.setdefault(person, [])
        if spans and spans[-1][1] == start:
            spans[-1] = (spans[-1][0], stop)
        else:
            spans.append((start, stop))

    for event in events:
        if event["club_code"] != club or event["play_type"] not in ("IN", "OUT"):
            continue
        person = event.get("person_code")
        if not person:
            continue
        previous = at = _at(event, previous)
        if event["play_type"] == "IN":
            on.setdefault(person, at)
        elif person in on:
            close(person, on.pop(person), at)
    for person, start in on.items():
        close(person, start, end)
    return intervals


def derive_rows(games, players, events):
    """Rows for `game_player_on_court`, sorted by game, side, player and interval."""
    by_game, roster = {}, {}
    for event in events:
        by_game.setdefault(event["game_code"], []).append(event)
    for player in players:
        roster.setdefault((player["game_code"], player["side"]), []).append(player)
    rows = []
    for game in sorted(games, key=lambda row: row["game_code"]):
        code = game["game_code"]
        if game.get("played") is not True or code not in by_game:
            continue
        ordered = sorted(by_game[code], key=_sort_key)
        end = _game_end(ordered)
        for side, club in (("local", game.get("local_club_code")),
                           ("road", game.get("road_club_code"))):
            team = roster.get((code, side), [])
            if not club or not team:
                continue
            starters = [p["person_key"] for p in team if p.get("started")]
            spans = _side_intervals(starters, ordered, club, end)
            for person in sorted(spans):
                for ordinal, (start, stop) in enumerate(spans[person], 1):
                    rows.append({"game_code": code, "side": side, "person_key": person,
                                 "interval_ordinal": ordinal, "club_code": club,
                                 "start_seconds": start, "end_seconds": stop})
    return rows


def read_rows(cursor, competition_code, season_code):
    scope = (competition_code, season_code)
    cursor.execute('SELECT * FROM "games" WHERE competition_code = %s AND season_code = %s',
                   scope)
    games = _dict_rows(cursor)
    cursor.execute('SELECT game_code, side, person_key, club_code, started '
                   'FROM "game_player_stats" WHERE competition_code = %s '
                   'AND season_code = %s', scope)
    players = _dict_rows(cursor)
    cursor.execute(f'SELECT {", ".join(EVENT_COLUMNS)} FROM "play_by_play" '
                   'WHERE competition_code = %s AND season_code = %s', scope)
    return derive_rows(games, players, _dict_rows(cursor))


def replace_season(connection, competition_code, season_code, rows):
    return _replace(connection, competition_code, season_code, rows, name=TABLE)


WARNING_QUERY = (
    'SELECT count(*) FROM "game_player_stats" AS s '
    'WHERE s.competition_code = %s AND s.season_code = %s AND s.seconds_played IS NOT NULL '
    'AND EXISTS (SELECT 1 FROM "game_player_on_court" AS g '
    'WHERE g.competition_code = s.competition_code AND g.season_code = s.season_code '
    'AND g.game_code = s.game_code) '
    'AND abs(s.seconds_played - COALESCE((SELECT sum(c.end_seconds - c.start_seconds) '
    'FROM "game_player_on_court" AS c WHERE c.competition_code = s.competition_code '
    'AND c.season_code = s.season_code AND c.game_code = s.game_code '
    'AND c.side = s.side AND c.person_key = s.person_key), 0)) > %s')


def check_season(connection, competition_code, season_code):
    """Read-only checks; returns (severity, code, table, count) for each failure."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass(%s)", (TABLE,))
        if cursor.fetchone()[0] is None:
            return [("ERROR", "missing_table", TABLE, 1)]
        expected = read_rows(cursor, competition_code, season_code)
        actual = stored_rows(cursor, TABLE, competition_code, season_code)
        issues = differences_from_derivation(
            TABLE, actual, expected,
            columns=("game_code", "side", "person_key", "interval_ordinal"))
        cursor.execute(WARNING_QUERY, (competition_code, season_code, TOLERANCE_SECONDS))
        differing = cursor.fetchone()[0]
    if differing:
        issues.append(("WARN", "seconds_differ_from_box_score", TABLE, differing))
    return issues


def run_seasons(config_path, competition, season_codes, dry_run=False, quality_only=False):
    return _run(config_path, competition, season_codes, dry_run, quality_only,
                read=read_rows, replace=replace_season, check=check_season)


def main(argv=None):
    return _main(argv, run=run_seasons,
                 description="Rebuild on-court intervals per player and game in silver.")


if __name__ == "__main__":
    sys.exit(main())
