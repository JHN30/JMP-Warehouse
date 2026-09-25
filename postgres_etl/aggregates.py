"""Season-scoped derived tables: team-season totals and data-coverage counts.

Mirrors ``getTeamStatsSummary`` and ``getCoverage`` in the jmp-euroleague2
Express backend (``backend/src/db/season-games.ts`` and
``season-coverage.ts``): same measures, same counting and status logic, with
one approved change — ``shotLocations`` and ``playByPlay`` are computed from
this pipeline's own ``app_shots``/``app_play_by_play`` data instead of
Express's current hardcoded ``unavailable`` (Express hasn't been updated for
feature 21 yet; that is a separate, coordinated fix on that side).

Unlike ``records.py``, these tables ARE season-scoped: a season's rows depend
only on that season's already-loaded local data, so a rebuild replaces one
season's rows at a time (DELETE that season, then insert), fitting the normal
per-season load and Neon publish path.
"""

import json

from flat_schema import TEAM_SEASON_MEASURES, create_index_sql, create_table_sql, physical_name, snake
from shared import COMPETITION_CODES, connect


AGGREGATE_TABLES = ("app_team_season_stats", "app_coverage_seasons", "app_coverage_games")

MEASURE_COLUMNS = tuple(snake(name) for name in TEAM_SEASON_MEASURES.split())

COVERAGE_ITEM_KEYS = ("boxScores", "periodScores", "officialStandings", "rosters",
                      "playerPhotos", "seasonStatistics", "shotLocations", "playByPlay")
COVERAGE_LABELS = {
    "boxScores": "Box scores", "periodScores": "Period scores",
    "officialStandings": "Official standings", "rosters": "Rosters",
    "playerPhotos": "Player photos", "seasonStatistics": "Season statistics",
    "shotLocations": "Shot locations", "playByPlay": "Play-by-play",
}
# officialStandings, rosters and seasonStatistics use "incomplete" for the
# not-yet-complete case; every other item uses "partial".
ROSTER_STYLE_ITEMS = frozenset({"officialStandings", "rosters", "seasonStatistics"})
# Season-wide items: their per-game row copies the season row's item verbatim.
SEASON_WIDE_ITEMS = frozenset({"officialStandings", "rosters", "seasonStatistics"})


def _status(key, available, applicable):
    if applicable == 0:
        return "notYetApplicable"
    if available == 0:
        return "unavailable"
    if available >= applicable:
        return "available"
    return "incomplete" if key in ROSTER_STYLE_ITEMS else "partial"


def _item(key, available, applicable):
    return {
        "key": key,
        "label": COVERAGE_LABELS[key],
        "status": _status(key, available, applicable),
        "availableCount": available,
        "applicableCount": applicable,
    }


TEAM_SEASON_COLUMNS = (
    ("competition_code", "season_code", "phase_code", "club_code", "club_name", "games_played")
    + tuple(f"own_{c}" for c in MEASURE_COLUMNS) + tuple(f"opp_{c}" for c in MEASURE_COLUMNS)
)


def _team_season_stats_select_sql():
    own_sums = ", ".join(f'sum(own."{c}") AS "own_{c}"' for c in MEASURE_COLUMNS)
    opp_sums = ", ".join(f'sum(opp."{c}") AS "opp_{c}"' for c in MEASURE_COLUMNS)
    stats = physical_name("game_team_stats")
    games = physical_name("games")
    return (
        "SELECT own.competition_code AS competition_code, own.season_code AS season_code, "
        "g.phase_code AS phase_code, "
        "CASE WHEN own.side = 'local' THEN g.local_club_code ELSE g.road_club_code END "
        "AS club_code, "
        "CASE WHEN own.side = 'local' THEN g.local_club_name ELSE g.road_club_name END "
        "AS club_name, "
        "count(DISTINCT own.game_code) AS games_played, " + own_sums + ", " + opp_sums + " "
        f'FROM "{stats}" AS own '
        f'JOIN "{games}" AS g ON g.competition_code = own.competition_code '
        "AND g.season_code = own.season_code AND g.game_code = own.game_code "
        f'JOIN "{stats}" AS opp ON opp.competition_code = own.competition_code '
        "AND opp.season_code = own.season_code AND opp.game_code = own.game_code "
        "AND opp.stats_kind = 'total' AND opp.side <> own.side "
        "WHERE own.competition_code = %(competition_code)s AND own.season_code = %(season_code)s "
        "AND own.stats_kind = 'total' AND g.played IS TRUE "
        "GROUP BY own.competition_code, own.season_code, g.phase_code, "
        "CASE WHEN own.side = 'local' THEN g.local_club_code ELSE g.road_club_code END, "
        "CASE WHEN own.side = 'local' THEN g.local_club_name ELSE g.road_club_name END"
    )


def _season_counts_sql():
    games = physical_name("games")
    game_team_stats = physical_name("game_team_stats")
    game_period_scores = physical_name("game_period_scores")
    clubs = physical_name("clubs")
    standings = physical_name("standings_basicstandings")
    registrations = physical_name("registrations")
    season_stats = physical_name("season_stats_traditional")
    game_player_stats = physical_name("game_player_stats")
    shots = physical_name("shots")
    play_by_play = physical_name("play_by_play")
    return (
        "WITH completed AS ("
        f'  SELECT count(*) AS n FROM "{games}" '
        "  WHERE competition_code = %(competition_code)s AND season_code = %(season_code)s "
        "  AND played IS TRUE"
        "), box AS ("
        f'  SELECT count(DISTINCT gts.game_code) AS n FROM "{game_team_stats}" AS gts '
        f'  JOIN "{games}" AS g ON g.competition_code = gts.competition_code '
        "  AND g.season_code = gts.season_code AND g.game_code = gts.game_code "
        "  WHERE gts.competition_code = %(competition_code)s AND gts.season_code = %(season_code)s "
        "  AND gts.stats_kind = 'total' AND g.played IS TRUE"
        "), period AS ("
        f'  SELECT count(DISTINCT gps.game_code) AS n FROM "{game_period_scores}" AS gps '
        f'  JOIN "{games}" AS g ON g.competition_code = gps.competition_code '
        "  AND g.season_code = gps.season_code AND g.game_code = gps.game_code "
        "  WHERE gps.competition_code = %(competition_code)s AND gps.season_code = %(season_code)s "
        "  AND g.played IS TRUE"
        "), clubs_count AS ("
        f'  SELECT count(*) AS n FROM "{clubs}" '
        "  WHERE competition_code = %(competition_code)s AND season_code = %(season_code)s"
        "), standings_clubs AS ("
        f'  SELECT count(DISTINCT club_code) AS n FROM "{standings}" '
        "  WHERE competition_code = %(competition_code)s AND season_code = %(season_code)s"
        "), roster_clubs AS ("
        f'  SELECT count(DISTINCT club_code) AS n FROM "{registrations}" '
        "  WHERE competition_code = %(competition_code)s AND season_code = %(season_code)s "
        "  AND club_code IS NOT NULL"
        "), stats_players AS ("
        f'  SELECT count(DISTINCT person_key) AS n FROM "{season_stats}" '
        "  WHERE competition_code = %(competition_code)s AND season_code = %(season_code)s"
        "), photo_players AS ("
        f'  SELECT count(DISTINCT gps.person_key) AS n FROM "{game_player_stats}" AS gps '
        f'  JOIN "{games}" AS g ON g.competition_code = gps.competition_code '
        "  AND g.season_code = gps.season_code AND g.game_code = gps.game_code "
        "  WHERE gps.competition_code = %(competition_code)s AND gps.season_code = %(season_code)s "
        "  AND g.played IS TRUE AND gps.headshot_url IS NOT NULL"
        "), shots_games AS ("
        f'  SELECT count(DISTINCT s.game_code) AS n FROM "{shots}" AS s '
        f'  JOIN "{games}" AS g ON g.competition_code = s.competition_code '
        "  AND g.season_code = s.season_code AND g.game_code = s.game_code "
        "  WHERE s.competition_code = %(competition_code)s AND s.season_code = %(season_code)s "
        "  AND g.played IS TRUE"
        "), pbp_games AS ("
        f'  SELECT count(DISTINCT p.game_code) AS n FROM "{play_by_play}" AS p '
        f'  JOIN "{games}" AS g ON g.competition_code = p.competition_code '
        "  AND g.season_code = p.season_code AND g.game_code = p.game_code "
        "  WHERE p.competition_code = %(competition_code)s AND p.season_code = %(season_code)s "
        "  AND g.played IS TRUE"
        ") "
        "SELECT completed.n, box.n, period.n, clubs_count.n, standings_clubs.n, roster_clubs.n, "
        "stats_players.n, photo_players.n, shots_games.n, pbp_games.n "
        "FROM completed, box, period, clubs_count, standings_clubs, roster_clubs, "
        "stats_players, photo_players, shots_games, pbp_games"
    )


def _season_items(counts):
    (completed, box, period, clubs_count, standings_clubs, roster_clubs,
     stats_players, photo_players, shots_games, pbp_games) = counts
    return [
        _item("boxScores", box, completed),
        _item("periodScores", period, completed),
        _item("officialStandings", standings_clubs, clubs_count),
        _item("rosters", roster_clubs, clubs_count),
        _item("playerPhotos", photo_players, completed),
        _item("seasonStatistics", stats_players, clubs_count),
        _item("shotLocations", shots_games, completed),
        _item("playByPlay", pbp_games, completed),
    ]


def _game_rows_sql():
    stats = physical_name("game_team_stats")
    period = physical_name("game_period_scores")
    player_stats = physical_name("game_player_stats")
    shots = physical_name("shots")
    play_by_play = physical_name("play_by_play")
    games = physical_name("games")
    return (
        "SELECT g.game_code, g.played, "
        "(box.game_code IS NOT NULL) AS has_box, "
        "COALESCE(period.n, 0) > 0 AS has_period, "
        "COALESCE(photo.n, 0) AS photo_n, "
        "(shots.game_code IS NOT NULL) AS has_shots, "
        "(pbp.game_code IS NOT NULL) AS has_pbp "
        f'FROM "{games}" AS g '
        "LEFT JOIN (SELECT DISTINCT game_code FROM "
        f'"{stats}" WHERE competition_code = %(competition_code)s '
        "AND season_code = %(season_code)s AND stats_kind = 'total') AS box "
        "ON box.game_code = g.game_code "
        "LEFT JOIN (SELECT game_code, count(*) AS n FROM "
        f'"{period}" WHERE competition_code = %(competition_code)s '
        "AND season_code = %(season_code)s GROUP BY game_code) AS period "
        "ON period.game_code = g.game_code "
        "LEFT JOIN (SELECT game_code, count(DISTINCT person_key) AS n FROM "
        f'"{player_stats}" WHERE competition_code = %(competition_code)s '
        "AND season_code = %(season_code)s AND headshot_url IS NOT NULL "
        "GROUP BY game_code) AS photo ON photo.game_code = g.game_code "
        "LEFT JOIN (SELECT DISTINCT game_code FROM "
        f'"{shots}" WHERE competition_code = %(competition_code)s '
        "AND season_code = %(season_code)s) AS shots ON shots.game_code = g.game_code "
        "LEFT JOIN (SELECT DISTINCT game_code FROM "
        f'"{play_by_play}" WHERE competition_code = %(competition_code)s '
        "AND season_code = %(season_code)s) AS pbp ON pbp.game_code = g.game_code "
        "WHERE g.competition_code = %(competition_code)s AND g.season_code = %(season_code)s"
    )


def _game_items(row, season_wide_items):
    game_code, played, has_box, has_period, photo_n, has_shots, has_pbp = row
    applicable = 1 if played else 0
    items = [
        _item("boxScores", 1 if played and has_box else 0, applicable),
        _item("periodScores", 1 if played and has_period else 0, applicable),
        season_wide_items["officialStandings"],
        season_wide_items["rosters"],
        _item("playerPhotos", photo_n if played else 0, applicable),
        season_wide_items["seasonStatistics"],
        _item("shotLocations", 1 if played and has_shots else 0, applicable),
        _item("playByPlay", 1 if played and has_pbp else 0, applicable),
    ]
    return game_code, items


def build_aggregates(config_path, season_codes, names=AGGREGATE_TABLES, competition="euroleague",
                     dry_run=False, log=print):
    """Recompute the requested aggregate tables for each season in
    ``season_codes``, one season at a time (DELETE that season's rows, then
    insert). Returns {(name, season_code): row_count}."""
    unknown = set(names) - set(AGGREGATE_TABLES)
    if unknown:
        raise ValueError("Unknown aggregate table(s): " + ", ".join(sorted(unknown)))
    competition_code = COMPETITION_CODES[competition]
    counts = {}
    connection = connect(config_path)
    try:
        if not dry_run:
            with connection.cursor() as cursor:
                for name in names:
                    cursor.execute(create_table_sql(name))
                    for statement in create_index_sql(name):
                        cursor.execute(statement)
            connection.commit()
        for season_code in season_codes:
            params = {"competition_code": competition_code, "season_code": season_code}
            if dry_run:
                connection.set_session(readonly=True)
                with connection.cursor() as cursor:
                    if "app_team_season_stats" in names:
                        cursor.execute(
                            f"SELECT count(*) FROM ({_team_season_stats_select_sql()}) AS probe",
                            params)
                        n = cursor.fetchone()[0]
                        counts[("app_team_season_stats", season_code)] = n
                        log(f"  {physical_name('app_team_season_stats')} [{season_code}]: "
                            f"{n:,} rows would be computed")
                    if "app_coverage_seasons" in names:
                        cursor.execute(_season_counts_sql(), params)
                        counts[("app_coverage_seasons", season_code)] = 1
                        log(f"  {physical_name('app_coverage_seasons')} [{season_code}]: "
                            "1 row would be computed")
                    if "app_coverage_games" in names:
                        cursor.execute(_game_rows_sql(), params)
                        n = len(cursor.fetchall())
                        counts[("app_coverage_games", season_code)] = n
                        log(f"  {physical_name('app_coverage_games')} [{season_code}]: "
                            f"{n:,} rows would be computed")
                connection.rollback()
                connection.set_session(readonly=False)
                continue
            with connection:
                with connection.cursor() as cursor:
                    if "app_team_season_stats" in names:
                        physical = physical_name("app_team_season_stats")
                        cursor.execute(
                            f'DELETE FROM "{physical}" WHERE competition_code = %(competition_code)s '
                            "AND season_code = %(season_code)s", params)
                        columns = ", ".join(f'"{c}"' for c in TEAM_SEASON_COLUMNS)
                        cursor.execute(
                            f'INSERT INTO "{physical}" ({columns}) {_team_season_stats_select_sql()}',
                            params)
                        cursor.execute(
                            f'SELECT count(*) FROM "{physical}" WHERE competition_code = '
                            "%(competition_code)s AND season_code = %(season_code)s", params)
                        counts[("app_team_season_stats", season_code)] = cursor.fetchone()[0]
                        log(f"  {physical} [{season_code}]: "
                            f"{counts[('app_team_season_stats', season_code)]:,} rows")
                    if "app_coverage_seasons" in names or "app_coverage_games" in names:
                        cursor.execute(_season_counts_sql(), params)
                        season_row = _season_items(cursor.fetchone())
                        season_by_key = {item["key"]: item for item in season_row}
                    if "app_coverage_seasons" in names:
                        physical = physical_name("app_coverage_seasons")
                        cursor.execute(
                            f'DELETE FROM "{physical}" WHERE competition_code = %(competition_code)s '
                            "AND season_code = %(season_code)s", params)
                        cursor.execute(
                            f'INSERT INTO "{physical}" (competition_code, season_code, items) '
                            "VALUES (%(competition_code)s, %(season_code)s, %(items)s)",
                            {**params, "items": json.dumps(season_row)})
                        counts[("app_coverage_seasons", season_code)] = 1
                        log(f"  {physical} [{season_code}]: 1 row")
                    if "app_coverage_games" in names:
                        physical = physical_name("app_coverage_games")
                        cursor.execute(
                            f'DELETE FROM "{physical}" WHERE competition_code = %(competition_code)s '
                            "AND season_code = %(season_code)s", params)
                        cursor.execute(_game_rows_sql(), params)
                        rows = cursor.fetchall()
                        insert_sql = (
                            f'INSERT INTO "{physical}" (competition_code, season_code, game_code, items) '
                            "VALUES (%(competition_code)s, %(season_code)s, %(game_code)s, %(items)s)"
                        )
                        for row in rows:
                            game_code, items = _game_items(row, season_by_key)
                            cursor.execute(insert_sql, {
                                **params, "game_code": game_code, "items": json.dumps(items),
                            })
                        counts[("app_coverage_games", season_code)] = len(rows)
                        log(f"  {physical} [{season_code}]: {len(rows):,} rows")
    finally:
        connection.close()
    return counts
