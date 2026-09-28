"""Shot zones per team and game (feature 19c): attempts, makes and points by zone code.

`derive_rows` is pure. It shares 19a's storage and season runner; nothing reads Gold or Neon.
"""

import sys

from possessions import (MADE, MISSED, _dict_rows, differences_from_derivation, main as _main,
                         replace_season as _replace, run_seasons as _run, stored_rows)

TABLE = "game_team_shot_zones"
KEY = ("game_code", "side", "zone")
SOURCE_TABLES = ("games", "shots")
# The shots feed uses the play-by-play shot types: E2008-E2014 also record layups, dunks and
# blocked attempts (19a), and with them the zone totals equal the box score.
FIELD_GOALS = MADE | MISSED


def derive_rows(games, shots):
    """Rows for `game_team_shot_zones`, sorted by game, side and zone."""
    by_game = {}
    for shot in shots:
        if shot.get("action_code") in FIELD_GOALS and shot.get("zone"):
            by_game.setdefault(shot["game_code"], []).append(shot)
    rows = []
    for game in sorted(games, key=lambda row: row["game_code"]):
        code = game["game_code"]
        if game.get("played") is not True or code not in by_game:
            continue
        sides = {game.get("local_club_code"): "local", game.get("road_club_code"): "road"}
        totals = {}
        for shot in by_game[code]:
            side = sides.get(shot.get("club_code"))
            if side is None:
                continue
            entry = totals.setdefault((side, shot["zone"]), {"attempts": 0, "made": 0,
                                                             "points": 0, "club": shot["club_code"]})
            entry["attempts"] += 1
            if (shot.get("points") or 0) > 0:
                entry["made"] += 1
                entry["points"] += shot["points"]
        for (side, zone), entry in sorted(totals.items()):
            rows.append({"game_code": code, "side": side, "zone": zone,
                         "club_code": entry["club"], "attempts": entry["attempts"],
                         "made": entry["made"], "points": entry["points"]})
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


def check_season(connection, competition_code, season_code):
    """Read-only checks; returns (severity, code, table, count) for each failure."""
    scope = (competition_code, season_code)
    with connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass(%s)", (TABLE,))
        if cursor.fetchone()[0] is None:
            return [("ERROR", "missing_table", TABLE, 1)]
        expected = read_rows(cursor, *scope)
        actual = stored_rows(cursor, TABLE, *scope)
    return differences_from_derivation(TABLE, actual, expected, KEY)


def run_seasons(config_path, competition, season_codes, dry_run=False, quality_only=False):
    return _run(config_path, competition, season_codes, dry_run, quality_only,
                read=read_rows, replace=replace_season, check=check_season)


def main(argv=None):
    return _main(argv, run=run_seasons, description=(
        "Derive shot zones per team and game in silver from the shots feed."))


if __name__ == "__main__":
    sys.exit(main())
