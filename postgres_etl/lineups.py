"""Lineup stints per team and game (feature 29b), from starters, substitutions and play-by-play.

A stint is a stretch of a game with the same five players on court for both teams. The lineups
come from the same substitution walk as feature 29a; possessions come from feature 19a's counted
possession state machine and points from the running score, both attributed to the stint that
was on court at the closing event. `derive_rows` is pure and shares 19a's storage and season
runner. Nothing reads Gold or Neon.
"""

import sys

from on_court import _at
from possessions import (CLOCKLESS_GAMES_SQL, _count, _dict_rows, _game_end, _sort_key,
                         events_by_game,
                         differences_from_derivation, main as _main,
                         replace_season as _replace, run_seasons as _run, stored_rows)

TABLE = "game_team_lineup_stints"
SOURCE_TABLES = ("games", "game_player_stats", "play_by_play")
TRIGGER_TABLES = SOURCE_TABLES
EVENT_COLUMNS = ("game_code", "period", "event_ordinal", "club_code", "person_code",
                 "play_type", "minute", "marker_time", "points_a", "points_b")
LINEUP_SIZE = 5
# A team-game whose complete stints cover less than this share of the game is reported.
COVERAGE_MINIMUM = 0.95


def _stint(start, lineup):
    return {"start": start, "end": None, "lineup": lineup, "points": [0, 0],
            "possessions": {"local": 0, "road": 0}, "events": 0}


def _walk(ordered, clubs, starters, end):
    """Stints of one game as dicts, in time order, and the stint of each event by `id`."""
    sides = {clubs["local"]: "local", clubs["road"]: "road"}
    on = {side: set(starters[side]) for side in ("local", "road")}

    def lineup():
        return tuple(tuple(sorted(on[side])) for side in ("local", "road"))

    stints, stint_of = [_stint(0, lineup())], {}
    score, previous, pending = [0, 0], 0, None

    def settle():
        nonlocal pending
        if pending is None:
            return
        if lineup() != stints[-1]["lineup"]:
            stints[-1]["end"] = pending
            stints.append(_stint(pending, lineup()))
        pending = None

    for event in ordered:
        if event["play_type"] in ("IN", "OUT"):
            side, person = sides.get(event["club_code"]), event.get("person_code")
            if side and person:
                previous = at = _at(event, previous)
                on[side].add(person) if event["play_type"] == "IN" else on[side].discard(person)
                pending = at if pending is None else pending
            continue
        settle()
        current = stint_of[id(event)] = stints[-1]
        current["events"] += 1
        for index, key in enumerate(("points_a", "points_b")):
            value = event.get(key)
            if value is not None:
                current["points"][index] += max(0, value - score[index])
                score[index] = value
    settle()
    stints[-1]["end"] = max(end, stints[-1]["start"])
    return stints, stint_of


def derive_rows(games, players, events):
    """Rows for `game_team_lineup_stints`, sorted by game, side and stint."""
    by_game, starters = events_by_game(events), {}
    for player in players:
        if player.get("started"):
            starters.setdefault((player["game_code"], player["side"]), []).append(
                player["person_key"])
    rows = []
    for game in sorted(games, key=lambda row: row["game_code"]):
        code = game["game_code"]
        clubs = {"local": game.get("local_club_code"), "road": game.get("road_club_code")}
        if game.get("played") is not True or code not in by_game or not all(clubs.values()):
            continue
        ordered = sorted(by_game[code], key=_sort_key)
        team = {side: starters.get((code, side), []) for side in clubs}
        stints, stint_of = _walk(ordered, clubs, team, _game_end(ordered))
        ends = []
        _count(ordered, set(clubs.values()), ends)
        for club, event in ends:
            stint = stint_of.get(id(event))
            if stint is not None:
                stint["possessions"]["local" if club == clubs["local"] else "road"] += 1
        ordinal = 0
        for stint in stints:
            if any(len(lineup) != LINEUP_SIZE for lineup in stint["lineup"]):
                continue
            if stint["end"] == stint["start"] and not (
                    stint["events"] or any(stint["points"])):
                continue
            ordinal += 1
            for side, other, own in (("local", "road", 0), ("road", "local", 1)):
                rows.append({
                    "game_code": code, "side": side, "stint_ordinal": ordinal,
                    "club_code": clubs[side], "opponent_club_code": clubs[other],
                    "start_seconds": stint["start"], "end_seconds": stint["end"],
                    "players": ",".join(stint["lineup"][own]),
                    "opponent_players": ",".join(stint["lineup"][1 - own]),
                    "possessions_for": stint["possessions"][side],
                    "possessions_against": stint["possessions"][other],
                    "points_for": stint["points"][own],
                    "points_against": stint["points"][1 - own]})
    return rows


def read_rows(cursor, competition_code, season_code):
    scope = (competition_code, season_code)
    cursor.execute('SELECT * FROM "games" WHERE competition_code = %s AND season_code = %s',
                   scope)
    games = _dict_rows(cursor)
    cursor.execute('SELECT game_code, side, person_key, started FROM "game_player_stats" '
                   'WHERE competition_code = %s AND season_code = %s', scope)
    players = _dict_rows(cursor)
    cursor.execute(f'SELECT {", ".join(EVENT_COLUMNS)} FROM "play_by_play" '
                   'WHERE competition_code = %s AND season_code = %s', scope)
    return derive_rows(games, players, _dict_rows(cursor))


def replace_season(connection, competition_code, season_code, rows):
    return _replace(connection, competition_code, season_code, rows, name=TABLE)


WARNING_QUERY = (
    'SELECT count(*) FROM "game_team_advanced" AS a '
    'LEFT JOIN (SELECT game_code, side, sum(end_seconds - start_seconds) AS covered '
    'FROM "game_team_lineup_stints" WHERE competition_code = %s AND season_code = %s '
    'GROUP BY game_code, side) AS s ON s.game_code = a.game_code AND s.side = a.side '
    'WHERE a.competition_code = %s AND a.season_code = %s AND a.game_minutes IS NOT NULL '
    'AND EXISTS (SELECT 1 FROM "play_by_play" AS p WHERE p.competition_code = a.competition_code '
    'AND p.season_code = a.season_code AND p.game_code = a.game_code) '
    f'AND a.game_code NOT IN ({CLOCKLESS_GAMES_SQL}) '
    'AND COALESCE(s.covered, 0) < %s * a.game_minutes * 60')


def check_season(connection, competition_code, season_code):
    """Read-only checks; returns (severity, code, table, count) for each failure."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass(%s)", (TABLE,))
        if cursor.fetchone()[0] is None:
            return [("ERROR", "missing_table", TABLE, 1)]
        expected = read_rows(cursor, competition_code, season_code)
        actual = stored_rows(cursor, TABLE, competition_code, season_code)
        issues = differences_from_derivation(
            TABLE, actual, expected, columns=("game_code", "side", "stint_ordinal"))
        cursor.execute(WARNING_QUERY, (competition_code, season_code) * 3
                       + (COVERAGE_MINIMUM,))
        uncovered = cursor.fetchone()[0]
    if uncovered:
        issues.append(("WARN", "stints_cover_little_of_the_game", TABLE, uncovered))
    return issues


def run_seasons(config_path, competition, season_codes, dry_run=False, quality_only=False):
    return _run(config_path, competition, season_codes, dry_run, quality_only,
                read=read_rows, replace=replace_season, check=check_season)


def main(argv=None):
    return _main(argv, run=run_seasons,
                 description="Derive lineup stints per team and game in silver.")


if __name__ == "__main__":
    sys.exit(main())
