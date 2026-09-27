"""Read-only, season-scoped checks for the column-first PostgreSQL tables."""

from dataclasses import dataclass
from time import monotonic

from aggregates import COVERAGE_ITEM_KEYS, MEASURE_COLUMNS
from flat_schema import TABLES, TEAM_STATS_TABLES, physical_name
from flat_transform import FlatSeason
from shared import COMPETITION_CODES, connect, elapsed


@dataclass(frozen=True)
class Check:
    code: str
    table: str
    query: str
    severity: str = "ERROR"
    # Other registered tables the query reads; the check is skipped when one
    # of them does not exist yet.
    requires: tuple[str, ...] = ()


SEASON_STATS_TABLES = ("season_stats_traditional", "season_stats_advanced",
                       "season_stats_scoring", "season_stats_misc")

# Tables where no rows is the good outcome, not a warning.
EMPTY_IS_NORMAL = {"game_stat_gaps"}

# Legacy live feeds use these ids for team/coach events, not for people.
LIVE_TEAM_MARKERS = "'^(AC|CO)_[AB]$'"


@dataclass(frozen=True)
class Issue:
    severity: str
    code: str
    table: str
    count: int


@dataclass
class Report:
    season_code: str
    counts: dict[str, int]
    issues: list[Issue]

    @property
    def passed(self):
        return not any(issue.severity == "ERROR" for issue in self.issues)


def scoped_count(table, predicate=None):
    """Build a count query from a registered table name and a fixed predicate."""
    query = (f'SELECT count(*) FROM "{physical_name(table)}" AS row '
             'WHERE row.competition_code = %s AND row.season_code = %s')
    return query + (f" AND ({predicate})" if predicate else "")


def season_stats_missing_query(table):
    """Count expected (phase, mode) feeds with no rows. The fetcher requests
    'all' plus every phase with played games in both modes, and an empty API
    answer (E2026 'all' perGame) would otherwise load silently."""
    return (
        "WITH scope AS (SELECT %s::text AS competition_code, %s::text AS season_code), "
        "expected AS (SELECT scope.competition_code, scope.season_code, phase.phase_code, "
        "mode.mode FROM scope CROSS JOIN LATERAL ("
        "SELECT 'all' AS phase_code UNION "
        f'SELECT g.phase_code FROM "{physical_name("games")}" AS g '
        "WHERE g.competition_code = scope.competition_code "
        "AND g.season_code = scope.season_code "
        "AND g.played IS TRUE AND g.phase_code IS NOT NULL) AS phase "
        "CROSS JOIN (VALUES ('accumulated'), ('perGame')) AS mode(mode)) "
        "SELECT count(*) FROM expected "
        f'WHERE NOT EXISTS (SELECT 1 FROM "{physical_name(table)}" AS row '
        "WHERE row.competition_code = expected.competition_code "
        "AND row.season_code = expected.season_code "
        "AND row.phase_code = expected.phase_code AND row.mode = expected.mode)"
    )


def team_stats_points_mismatch_query():
    """Count clubs whose API accumulated points (own or opponents) differ from
    the totals summed from box scores in app_team_season_stats, per phase."""
    def feed_join(alias, name):
        return (f'JOIN "{physical_name(name)}" AS {alias} '
                f"ON {alias}.competition_code = agg.competition_code "
                f"AND {alias}.season_code = agg.season_code "
                f"AND {alias}.phase_code = agg.phase_code "
                f"AND {alias}.club_code = agg.club_code AND {alias}.mode = 'accumulated' ")
    return (
        f'SELECT count(*) FROM "{physical_name("app_team_season_stats")}" AS agg '
        + feed_join("own", "season_team_stats_traditional")
        + feed_join("opp", "season_team_stats_opponents_traditional")
        + "WHERE agg.competition_code = %s AND agg.season_code = %s "
        "AND (own.points_scored IS DISTINCT FROM agg.own_points "
        "OR opp.points_scored IS DISTINCT FROM agg.opp_points)"
    )


def orphan_query(child, parent, key, condition=""):
    """Find child rows whose in-scope parent key does not exist."""
    return (
        f'SELECT count(*) FROM "{physical_name(child)}" AS child '
        f'LEFT JOIN "{physical_name(parent)}" AS parent '
        'ON parent.competition_code = child.competition_code '
        'AND parent.season_code = child.season_code '
        f'AND parent."{key}" = child."{key}" '
        'WHERE child.competition_code = %s AND child.season_code = %s '
        f'AND child."{key}" IS NOT NULL AND parent."{key}" IS NULL'
        + (f" AND ({condition})" if condition else "")
    )


def checks_for_tables(names):
    """Only compare tables participating in this load, so partial loads are valid."""
    names = set(names)
    checks = []
    if "games" in names:
        checks.extend((
            Check("played_missing_score", "games", scoped_count(
                "games", "row.played IS TRUE AND (row.local_score IS NULL "
                         "OR row.road_score IS NULL)")),
            Check("played_missing_winner", "games", scoped_count(
                "games", "row.played IS TRUE AND row.match_winner_club_code IS NULL")),
            Check("played_missing_identity", "games", scoped_count(
                "games", "row.played IS TRUE AND (row.scheduled_at IS NULL "
                         "OR row.local_club_code IS NULL OR row.road_club_code IS NULL)")),
            Check("unplayed_has_result", "games", scoped_count(
                "games", "row.played IS FALSE AND (row.local_score IS NOT NULL "
                         "OR row.road_score IS NOT NULL "
                         "OR row.match_winner_club_code IS NOT NULL)")),
        ))
        for name in TABLES:
            if name in names and name != "games" and "game_code" in TABLES[name].key:
                checks.append(Check("orphan_game", name, orphan_query(name, "games", "game_code")))
    if {"games", "clubs"} <= names:
        for side in ("local", "road"):
            key = f"{side}_club_code"
            checks.append(Check(f"orphan_{side}_club", "games", (
                f'SELECT count(*) FROM "{physical_name("games")}" AS child '
                f'LEFT JOIN "{physical_name("clubs")}" AS parent '
                'ON parent.competition_code = child.competition_code '
                'AND parent.season_code = child.season_code '
                f'AND parent.club_code = child."{key}" '
                'WHERE child.competition_code = %s AND child.season_code = %s '
                f'AND child."{key}" IS NOT NULL AND parent.club_code IS NULL'
            )))
    if "people" in names:
        for child in ("registrations", "game_player_stats"):
            if child in names:
                checks.append(Check("orphan_person", child,
                                    orphan_query(child, "people", "person_key")))
    if {"game_player_stats", "clubs"} <= names:
        checks.append(Check("orphan_club", "game_player_stats",
                            orphan_query("game_player_stats", "clubs", "club_code")))
    if {"app_standings", "standings_basicstandings"} <= names:
        # The page table must have exactly one row per basicstandings row.
        checks.append(Check("app_standings_key_mismatch", "app_standings", (
            'SELECT count(*) FROM "app_standings" AS page '
            f'FULL JOIN "{physical_name("standings_basicstandings")}" AS basic '
            'ON basic.competition_code = page.competition_code '
            'AND basic.season_code = page.season_code '
            'AND basic.phase_code = page.phase_code '
            'AND basic.round_number = page.round_number '
            'AND basic.club_code = page.club_code '
            'WHERE COALESCE(page.competition_code, basic.competition_code) = %s '
            'AND COALESCE(page.season_code, basic.season_code) = %s '
            'AND (page.club_code IS NULL OR basic.club_code IS NULL)'
        )))
    if "app_team_season_stats" in names:
        negative = " OR ".join(
            f'row."own_{c}" < 0 OR row."opp_{c}" < 0' for c in MEASURE_COLUMNS)
        checks.append(Check("team_season_stats_negative", "app_team_season_stats", scoped_count(
            "app_team_season_stats", f"row.games_played < 0 OR {negative}")))
    for name in ("app_coverage_seasons", "app_coverage_games"):
        if name in names:
            keys_literal = ", ".join(f"'{key}'" for key in COVERAGE_ITEM_KEYS)
            checks.append(Check(f"{name}_item_keys", name, scoped_count(
                name,
                "(SELECT array_agg(elem->>'key' ORDER BY ordinality) "
                "FROM jsonb_array_elements(row.items) WITH ORDINALITY AS t(elem, ordinality)) "
                f"IS DISTINCT FROM ARRAY[{keys_literal}]"
            )))
            checks.append(Check(f"{name}_item_status", name, (
                f'SELECT count(*) FROM "{physical_name(name)}" AS row, '
                "jsonb_array_elements(row.items) AS elem "
                "WHERE row.competition_code = %s AND row.season_code = %s "
                "AND (elem->>'status') NOT IN "
                "('available', 'partial', 'incomplete', 'unavailable', 'notYetApplicable')"
            )))
    if {"app_coverage_games", "games"} <= names:
        checks.append(Check("app_coverage_games_key_mismatch", "app_coverage_games", (
            'SELECT count(*) FROM "app_coverage_games" AS page '
            f'FULL JOIN "{physical_name("games")}" AS g '
            'ON g.competition_code = page.competition_code '
            'AND g.season_code = page.season_code '
            'AND g.game_code = page.game_code '
            'WHERE COALESCE(page.competition_code, g.competition_code) = %s '
            'AND COALESCE(page.season_code, g.season_code) = %s '
            'AND (page.game_code IS NULL OR g.game_code IS NULL)'
        )))
    if "app_postseason_series" in names:
        checks.append(Check("postseason_series_wins_out_of_range", "app_postseason_series",
                            scoped_count("app_postseason_series",
                                         "row.club_a_wins < 0 OR row.club_b_wins < 0 "
                                         "OR row.club_a_wins > row.games_played "
                                         "OR row.club_b_wins > row.games_played")))
        checks.append(Check("postseason_series_winner_mismatch", "app_postseason_series",
                            scoped_count("app_postseason_series",
                                         "row.winner_club_code IS NOT NULL AND ("
                                         "row.winner_club_code NOT IN (row.club_a_code, row.club_b_code) "
                                         "OR (row.winner_club_code = row.club_a_code "
                                         "AND row.club_a_wins <= row.club_b_wins) "
                                         "OR (row.winner_club_code = row.club_b_code "
                                         "AND row.club_b_wins <= row.club_a_wins))")))
        checks.append(Check("postseason_series_game_club_mismatch", "app_postseason_series", (
            'SELECT count(*) FROM "app_postseason_series" AS row, '
            "jsonb_array_elements(row.games) AS g "
            "WHERE row.competition_code = %s AND row.season_code = %s "
            "AND NOT ((g->>'localClubCode') IN (row.club_a_code, row.club_b_code) "
            "AND (g->>'roadClubCode') IN (row.club_a_code, row.club_b_code))"
        )))
    checks.extend(anomaly_checks(names))
    return checks


def anomaly_checks(names):
    """Warnings that keep source gaps visible without blocking a publish."""
    checks = []
    if "app_team_season_stats" in names:
        # Runs with the aggregates, after they are rebuilt from the box scores.
        checks.append(Check("team_stats_points_mismatch", "season_team_stats_traditional",
                            team_stats_points_mismatch_query(), "WARN",
                            requires=("season_team_stats_traditional",
                                      "season_team_stats_opponents_traditional")))
    if "games" in names:
        checks.append(Check("attendance_not_recorded", "games", scoped_count(
            "games", "row.audience_note IS NOT NULL"), "WARN"))
        checks.append(Check("cancelled_inferred", "games", scoped_count(
            "games", "row.status = 'cancelled' AND row.status_note LIKE '%%inferred%%'"), "WARN"))
    for name in ("play_by_play", "shots"):
        if {"games", name} <= names:
            # The live API has data from E2007; earlier seasons have none by design.
            checks.append(Check(f"played_game_without_{name}", "games", (
                f'SELECT count(*) FROM "{physical_name("games")}" AS row '
                'WHERE row.competition_code = %s AND row.season_code = %s '
                'AND row.played IS TRUE AND substring(row.season_code from 2)::int >= 2007 '
                f'AND NOT EXISTS (SELECT 1 FROM "{physical_name(name)}" AS child '
                'WHERE child.competition_code = row.competition_code '
                'AND child.season_code = row.season_code AND child.game_code = row.game_code)'
            ), "WARN"))
    if "game_stat_gaps" in names:
        checks.append(Check("game_without_player_box_score", "game_stat_gaps", scoped_count(
            "game_stat_gaps", "row.stat_name = '*'"), "WARN"))
        checks.append(Check("unrecorded_stat_nulled", "game_stat_gaps", scoped_count(
            "game_stat_gaps", "row.stat_name <> '*'"), "WARN"))
    if "standings_basicstandings" in names:
        checks.append(Check("standings_played_not_won_plus_lost", "standings_basicstandings",
                            scoped_count("standings_basicstandings",
                                         "row.games_played <> row.games_won + row.games_lost"),
                            "WARN"))
    if "people" in names:
        checks.append(Check("fallback_person_key", "people", scoped_count(
            "people", "row.person_key LIKE 'anonymous-%%'"), "WARN"))
    for name in ("game_player_stats", *SEASON_STATS_TABLES):
        if name in names:
            checks.append(Check("fallback_person_key", name, scoped_count(
                name, "row.person_key LIKE 'unknown-%%'"), "WARN"))
    for name in (*SEASON_STATS_TABLES, *TEAM_STATS_TABLES):
        if {"games", name} <= names:
            checks.append(Check("season_stats_phase_mode_missing", name,
                                season_stats_missing_query(name), "WARN"))
    if "people" in names:
        for name in ("play_by_play", "shots"):
            if name in names:
                checks.append(Check("unmatched_live_player", name, (
                    f'SELECT count(*) FROM "{physical_name(name)}" AS child '
                    f'LEFT JOIN "{physical_name("people")}" AS parent '
                    'ON parent.competition_code = child.competition_code '
                    'AND parent.season_code = child.season_code '
                    'AND parent.person_key = child.person_code '
                    'WHERE child.competition_code = %s AND child.season_code = %s '
                    'AND child.player_code IS NOT NULL AND parent.person_key IS NULL '
                    f'AND child.player_code !~ {LIVE_TEAM_MARKERS}'
                ), "WARN"))
    for name in ("play_by_play", "shots"):
        if name in names:
            # Live ids that are not simply "P" + person code were matched another way.
            checks.append(Check("live_player_matched_by_fallback", name, scoped_count(
                name, "row.person_code_method NOT IN ('live_id')"), "WARN"))
    return checks


def _exists(cursor, name):
    cursor.execute("SELECT to_regclass(%s)", (physical_name(name),))
    return cursor.fetchone()[0] is not None


def check_season(connection, competition, season_code, names):
    """Return counts and actionable issues without modifying PostgreSQL."""
    unknown = set(names) - set(TABLES)
    if unknown:
        raise ValueError("Unknown quality-check table(s): " + ", ".join(sorted(unknown)))
    names = list(dict.fromkeys(names))
    scope = (COMPETITION_CODES[competition], season_code)
    counts = {}
    issues = []
    with connection.cursor() as cursor:
        for name in names:
            if not _exists(cursor, name):
                issues.append(Issue("ERROR", "missing_table", name, 1))
                continue
            cursor.execute(scoped_count(name), scope)
            count = cursor.fetchone()[0]
            counts[name] = count
            if count == 0 and name not in EMPTY_IS_NORMAL:
                issues.append(Issue("WARN", "empty_table", name, 0))
        for check in checks_for_tables(counts):
            if any(not _exists(cursor, name) for name in check.requires):
                continue
            cursor.execute(check.query, scope)
            count = cursor.fetchone()[0]
            if count:
                issues.append(Issue(check.severity, check.code, check.table, count))
    return Report(season_code, counts, issues)


def validate_loaded(config_path, data_root, competition, season_codes, names):
    """Validate every selected season after loading, or on demand."""
    connection = connect(config_path)
    passed = True
    started = monotonic()
    try:
        connection.set_session(readonly=True, isolation_level="REPEATABLE READ")
        for season_code in season_codes:
            season = FlatSeason(data_root, competition, season_code)
            loaded_names = [name for name in names if season.files(name)]
            if not loaded_names:
                print(f"Quality {season_code}: no selected source files; nothing to check",
                      flush=True)
                continue
            report = check_season(connection, competition, season_code, loaded_names)
            passed &= report.passed
            errors = sum(issue.severity == "ERROR" for issue in report.issues)
            warnings = sum(issue.severity == "WARN" for issue in report.issues)
            print(f"Quality {season_code}: {len(report.counts)} table(s), "
                  f"{sum(report.counts.values()):,} rows, {errors} error(s), "
                  f"{warnings} warning(s) | elapsed {elapsed(started)}", flush=True)
            for issue in report.issues:
                print(f"  {issue.severity} {physical_name(issue.table)}: "
                      f"{issue.code} ({issue.count:,} row(s))", flush=True)
            connection.rollback()  # Fresh read-only snapshot for the next season.
    finally:
        connection.close()
    return passed


def validate_aggregates(config_path, competition, season_codes, names):
    """Validate season-scoped derived tables (aggregates.py). Unlike
    validate_loaded, there are no bronze source files to gate on: these
    tables are computed from other already-loaded local tables."""
    connection = connect(config_path)
    passed = True
    started = monotonic()
    try:
        connection.set_session(readonly=True, isolation_level="REPEATABLE READ")
        for season_code in season_codes:
            report = check_season(connection, competition, season_code, names)
            passed &= report.passed
            errors = sum(issue.severity == "ERROR" for issue in report.issues)
            warnings = sum(issue.severity == "WARN" for issue in report.issues)
            print(f"Quality {season_code}: {len(report.counts)} table(s), "
                  f"{sum(report.counts.values()):,} rows, {errors} error(s), "
                  f"{warnings} warning(s) | elapsed {elapsed(started)}", flush=True)
            for issue in report.issues:
                print(f"  {issue.severity} {physical_name(issue.table)}: "
                      f"{issue.code} ({issue.count:,} row(s))", flush=True)
            connection.rollback()
    finally:
        connection.close()
    return passed
