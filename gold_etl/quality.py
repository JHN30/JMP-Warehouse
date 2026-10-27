"""Read-only, scope-specific equality checks for Gold source projections."""

from collections import defaultdict

from gold_etl.schema import physical_name
from gold_etl.schema import (COPIED_TABLES, PLAYER_STATS, columns, count_sql, scope_predicate,
                             source_columns)
from gold_etl.game_advanced import PER_FLOOR_SECONDS
from gold_etl.per_game_rows import OWN_COLUMNS, derive_per_game
from gold_etl.qualification import EUROCUP_GROUP_PHASES, postseason_phases, scope_min_games, scope_rounds
from gold_etl.postseason import TABLES as PS_TABLES, _dict_rows, read_rows as read_postseason_rows
from gold_etl.standings import KEY as STANDINGS_KEY, read_rows as read_standings_rows
from gold_etl.schema import STANDINGS_FEEDS, TEAM_PBP_ADDITIVE
from gold_etl.schema import GOLD_TABLES, SEASON_DERIVED_NAMES, WINDOWS, IDENTITY_TABLES, RECORDS_TABLES
from gold_etl.loader import read_aggregate_rows
from gold_etl.records import read_rows as read_record_rows
from gold_etl.identity import read_rows as read_identity_rows
from gold_etl.registrations import read_rows as read_registration_rows
from gold_etl.series import read_rows as read_series_rows
from gold_etl.team_rounds import read_rows as read_round_rows


def check_scope(cursor, name, competition_code, season_code):
    """Return actionable issues; PKs and equal row counts make one-way EXCEPT sufficient."""
    if name not in COPIED_TABLES:
        raise ValueError(f"Unknown Gold source table: {name}")
    cursor.execute("SELECT to_regclass(%s)", (f"gold.{physical_name(name)}",))
    if cursor.fetchone()[0] is None:
        return [f"gold.{physical_name(name)} is missing"]
    if name == "registrations":
        return check_registrations(cursor, competition_code, season_code)
    scope = (competition_code, season_code)
    cursor.execute(count_sql(name, "silver"), scope)
    source_count = cursor.fetchone()[0]
    cursor.execute(count_sql(name, "gold"), scope)
    gold_count = cursor.fetchone()[0]
    issues = []
    if source_count != gold_count:
        issues.append(f"gold.{physical_name(name)} {season_code}: {gold_count} rows; "
                      f"silver has {source_count}")
    field_list = ", ".join(f'"{column}"' for column in source_columns(name))
    cursor.execute(
        f'SELECT EXISTS (SELECT {field_list} FROM silver."{name}" '
        f'WHERE {scope_predicate(name)} EXCEPT '
        f'SELECT {field_list} FROM gold."{physical_name(name)}" '
        f'WHERE {scope_predicate(name, feed_only=True)})', scope + scope,
    )
    if cursor.fetchone()[0]:
        issues.append(f"gold.{physical_name(name)} {season_code}: source-column values differ from silver")
    return issues


def check_registrations(cursor, competition_code, season_code):
    """Gold holds exactly the collapsed Silver registrations, one row per group."""
    name = "registrations"
    expected = read_registration_rows(cursor, competition_code, season_code)
    fields = ", ".join(f'"{field}"' for field in columns(name))
    cursor.execute(f'SELECT {fields} FROM gold."{physical_name(name)}" '
                   f'WHERE {scope_predicate(name)}', (competition_code, season_code))
    actual = _dict_rows(cursor)
    by_key = lambda rows: {row["registration_key"]: row for row in rows}
    if len(actual) != len(expected) or by_key(actual).keys() != by_key(expected).keys():
        return [f"gold.{physical_name(name)} {season_code}: keys differ from collapsed Silver "
                f"({len(actual)} Gold, {len(expected)} expected)"]
    if by_key(actual) != by_key(expected):
        return [f"gold.{physical_name(name)} {season_code}: values differ from collapsed Silver"]
    return []


def check_player_stats_flags(cursor, name, competition_code, season_code):
    """Verify qualification columns and that calculated perGame rows follow their accumulated row."""
    if name not in PLAYER_STATS:
        raise ValueError(f"Not a season player table: {name}")
    cursor.execute("SELECT to_regclass(%s)", (f"gold.{physical_name(name)}",))
    if cursor.fetchone()[0] is None:
        return [f"gold.{physical_name(name)} is missing"]
    fields = ", ".join(f'"{field}"' for field in columns(name))
    cursor.execute(f'SELECT {fields} FROM gold."{physical_name(name)}" '
                   "WHERE competition_code = %s AND season_code = %s",
                   (competition_code, season_code))
    rows = _dict_rows(cursor)
    rounds = scope_rounds(cursor, competition_code, season_code)
    return player_stats_issues(name, season_code, rows, rounds)


def player_stats_issues(name, season_code, rows, rounds):
    issues = []
    label = f"gold.{physical_name(name)} {season_code}"
    thresholds = defaultdict(set)
    accumulated, per_game = {}, {}
    for row in rows:
        phase = row["phase_code"]
        thresholds[(phase, row["mode"])].add(row["min_games"])
        if row["qualified"] != (row["games_played"] >= row["min_games"]):
            issues.append(f"{label} {phase} {row['mode']} {row['person_key']}: "
                          "qualified does not match games_played >= min_games")
        (accumulated if row["mode"] == "accumulated" else per_game)[
            (phase, row["person_key"])] = row
    for (phase, mode), values in sorted(thresholds.items()):
        expected = scope_min_games(rounds, phase, season_code)
        if values != {expected}:
            issues.append(f"{label} {phase} {mode}: min_games {sorted(values)}, expected {expected}")
    for key in sorted(accumulated):
        if key not in per_game:
            issues.append(f"{label} {key[0]} {key[1]}: accumulated row has no perGame row")
    for key in sorted(per_game):
        row = per_game[key]
        if row["is_calculated"] and key[0] != "PS" and key in accumulated:
            expected = derive_per_game(name, accumulated[key])
            differing = sorted(column for column in expected if column not in OWN_COLUMNS
                               and expected[column] != row[column])
            if differing:
                issues.append(f"{label} {key[0]} {key[1]}: calculated perGame row differs "
                              f"from its accumulated row in {', '.join(differing)}")
    return issues


def check_player_stats_warnings(cursor, name, competition_code, season_code):
    """Feed perGame rows below min_games: the rule does not reproduce that feed scope."""
    cursor.execute(
        f'SELECT phase_code, count(*) FROM gold."{physical_name(name)}" '
        "WHERE competition_code = %s AND season_code = %s AND mode = 'perGame' "
        'AND is_calculated IS FALSE AND NOT qualified GROUP BY phase_code ORDER BY phase_code',
        (competition_code, season_code))
    return [f"gold.{physical_name(name)} {season_code} {phase}: {count} feed perGame row(s) below min_games"
            for phase, count in cursor.fetchall()]


def check_postseason_scope(cursor, name, competition_code, season_code):
    """Compare the complete derived PS slice with fresh Silver calculations."""
    if name not in PS_TABLES:
        raise ValueError(f"No postseason derivation for {name}")
    cursor.execute("SELECT to_regclass(%s)", (f"gold.{physical_name(name)}",))
    if cursor.fetchone()[0] is None:
        return [f"gold.{physical_name(name)} is missing"]
    expected = read_postseason_rows(cursor, competition_code, season_code)[name]
    field_list = ", ".join(f'"{field}"' for field in columns(name))
    cursor.execute(
        f'SELECT {field_list} FROM gold."{physical_name(name)}" '
        "WHERE competition_code = %s AND season_code = %s AND phase_code = 'PS'",
        (competition_code, season_code),
    )
    actual = _dict_rows(cursor)
    for row in expected:
        row["competition_code"] = competition_code
        row["season_code"] = season_code
    if len(actual) != len(expected):
        return [f"gold.{physical_name(name)} PS {season_code}: {len(actual)} rows; "
                f"Silver derivation expects {len(expected)}"]
    by_key = lambda rows: {(row["mode"], row["entry_ordinal"]): row for row in rows}
    if by_key(actual) != by_key(expected):
        return [f"gold.{physical_name(name)} PS {season_code}: derived keys or values differ from Silver"]
    return []


def check_standings_scope(cursor, competition_code, season_code):
    """Compare every page key and field/list value with Silver derivation."""
    name = "app_standings"
    cursor.execute("SELECT to_regclass(%s)", ("gold.app_standings",))
    if cursor.fetchone()[0] is None:
        return ["gold.app_standings is missing"]
    expected = read_standings_rows(cursor, competition_code, season_code)
    fields = ", ".join(f'"{field}"' for field in columns(name))
    cursor.execute(
        f'SELECT {fields} FROM gold."{physical_name(name)}" '
        'WHERE competition_code = %s AND season_code = %s',
        (competition_code, season_code),
    )
    actual = _dict_rows(cursor)
    by_key = lambda rows: {tuple(row[column] for column in STANDINGS_KEY): row
                           for row in rows}
    if by_key(actual).keys() != by_key(expected).keys():
        return [f"gold.app_standings {season_code}: keys differ from silver.standings_basic "
                f"({len(actual)} Gold, {len(expected)} Silver)"]
    if by_key(actual) != by_key(expected):
        return [f"gold.app_standings {season_code}: feed fields or lists differ from Silver"]
    return []


def standings_feed_lag(rows, season_code):
    """Warnings where the standings feeds of one round disagree on games played or won.

    The API caches each feed on its own clock, so one can answer a game behind the
    others. The most advanced value in the round is the current one; the feeds
    below it are named with an example club.
    """
    prefixes = [prefix for _, prefix in STANDINGS_FEEDS]
    lags = {}
    for row in rows:
        for measure in ("games_played", "games_won"):
            values = {prefix: row.get(f"{prefix}_{measure}") for prefix in prefixes}
            values = {prefix: value for prefix, value in values.items() if value is not None}
            if not values:
                continue
            current = max(values.values())
            for prefix, value in values.items():
                if value < current:
                    lags.setdefault((row["phase_code"], row["round_number"], measure, prefix),
                                    []).append(f'{row["club_code"]}: {value} vs {current}')
    return [f"gold.app_standings {season_code} {phase} round {round_number}: {prefix}_{measure} "
            f"is behind the other feeds for {len(examples)} club(s) (e.g. {examples[0]}); "
            "the API answered a stale feed, refresh again later"
            for (phase, round_number, measure, prefix), examples in sorted(lags.items())]


def check_standings_feeds(cursor, competition_code, season_code):
    """Warnings for standings feeds that lag each other, derived from Silver."""
    return standings_feed_lag(read_standings_rows(cursor, competition_code, season_code),
                              season_code)


def check_aggregate_scope(cursor, name, competition_code, season_code):
    """Compare every derived key and value with a fresh Silver calculation."""
    if name not in SEASON_DERIVED_NAMES:
        raise ValueError(f"Unknown Gold aggregate table: {name}")
    cursor.execute("SELECT to_regclass(%s)", (f"gold.{physical_name(name)}",))
    if cursor.fetchone()[0] is None:
        return [f"gold.{physical_name(name)} is missing"]
    expected = read_aggregate_rows(cursor, name, competition_code, season_code)
    for row in expected:
        row["competition_code"] = competition_code
        row["season_code"] = season_code
    fields = ", ".join(f'"{field}"' for field in columns(name))
    cursor.execute(
        f'SELECT {fields} FROM gold."{physical_name(name)}" '
        'WHERE competition_code = %s AND season_code = %s',
        (competition_code, season_code),
    )
    actual = _dict_rows(cursor)
    key = GOLD_TABLES[name].key
    by_key = lambda rows: {tuple(row[column] for column in key): row for row in rows}
    if len(actual) != len(expected) or by_key(actual).keys() != by_key(expected).keys():
        return [f"gold.{physical_name(name)} {season_code}: keys differ from Silver derivation "
                f"({len(actual)} Gold, {len(expected)} expected)"]
    if by_key(actual) != by_key(expected):
        return [f"gold.{physical_name(name)} {season_code}: derived values differ from Silver"]
    return []


def check_records_scope(cursor, name, competition_code):
    """Compare every leaderboard key and value with all loaded Silver seasons."""
    if name not in RECORDS_TABLES:
        raise ValueError(f"Unknown Gold records table: {name}")
    cursor.execute("SELECT to_regclass(%s)", (f"gold.{physical_name(name)}",))
    if cursor.fetchone()[0] is None:
        return [f"gold.{physical_name(name)} is missing"]
    expected = read_record_rows(cursor, name, competition_code)
    fields = ", ".join(f'"{field}"' for field in columns(name))
    cursor.execute(f'SELECT {fields} FROM gold."{physical_name(name)}" WHERE competition_code = %s',
                   (competition_code,))
    actual = _dict_rows(cursor)
    key = GOLD_TABLES[name].key
    by_key = lambda rows: {tuple(row[field] for field in key): row for row in rows}
    if len(actual) != len(expected) or by_key(actual).keys() != by_key(expected).keys():
        return [f"gold.{physical_name(name)}: keys differ from Silver derivation "
                f"({len(actual)} Gold, {len(expected)} expected)"]
    if by_key(actual) != by_key(expected):
        return [f"gold.{physical_name(name)}: record values differ from Silver"]
    return []


def check_identity_scope(cursor, name, competition_code):
    """Compare every identity key and value with complete Silver history."""
    if name not in IDENTITY_TABLES:
        raise ValueError(f"Unknown Gold identity table: {name}")
    cursor.execute("SELECT to_regclass(%s)", (f"gold.{physical_name(name)}",))
    if cursor.fetchone()[0] is None:
        return [f"gold.{physical_name(name)} is missing"]
    expected = read_identity_rows(cursor, name, competition_code)
    fields = ", ".join(f'"{field}"' for field in columns(name))
    cursor.execute(f'SELECT {fields} FROM gold."{physical_name(name)}" WHERE competition_code = %s',
                   (competition_code,))
    actual = _dict_rows(cursor)
    key = GOLD_TABLES[name].key
    by_key = lambda rows: {tuple(row[field] for field in key): row for row in rows}
    if len(actual) != len(expected) or by_key(actual).keys() != by_key(expected).keys():
        return [f"gold.{physical_name(name)}: keys differ from Silver derivation "
                f"({len(actual)} Gold, {len(expected)} expected)"]
    if by_key(actual) != by_key(expected):
        return [f"gold.{physical_name(name)}: identity values differ from Silver"]
    return []


def check_postseason_phases(cursor, competition_code, season_code):
    """EuroCup played games in a phase that is neither a group stage nor postseason,
    so a new API phase code is seen instead of being left out of PS and series."""
    if not season_code.startswith("U"):
        return []
    known = sorted(EUROCUP_GROUP_PHASES | postseason_phases(season_code))
    cursor.execute(
        "SELECT phase_code, count(*) FROM silver.games WHERE competition_code = %s "
        "AND season_code = %s AND played IS TRUE AND NOT (phase_code = ANY(%s)) "
        "GROUP BY phase_code ORDER BY phase_code", (competition_code, season_code, known))
    return [f"silver.games {season_code} {phase}: {count} played game(s) in a phase that is "
            "neither a EuroCup group stage nor postseason" for phase, count in cursor.fetchall()]


def check_series_scope(cursor, competition_code, season_code):
    """Compare pairing keys, counts and ordered game JSON with Silver."""
    name = "app_postseason_series"
    cursor.execute("SELECT to_regclass(%s)", (f"gold.{physical_name(name)}",))
    if cursor.fetchone()[0] is None:
        return [f"gold.{physical_name(name)} is missing"]
    expected = read_series_rows(cursor, competition_code, season_code)
    for row in expected:
        row["competition_code"] = competition_code
        row["season_code"] = season_code
    fields = ", ".join(f'"{field}"' for field in columns(name))
    cursor.execute(f'SELECT {fields} FROM gold."{physical_name(name)}" '
                   'WHERE competition_code = %s AND season_code = %s',
                   (competition_code, season_code))
    actual = _dict_rows(cursor)
    key = GOLD_TABLES[name].key
    by_key = lambda rows: {tuple(row[field] for field in key): row for row in rows}
    if len(actual) != len(expected) or by_key(actual).keys() != by_key(expected).keys():
        return [f"gold.{physical_name(name)} {season_code}: keys differ from Silver derivation "
                f"({len(actual)} Gold, {len(expected)} expected)"]
    if by_key(actual) != by_key(expected):
        return [f"gold.{physical_name(name)} {season_code}: values or games differ from Silver"]
    return []


# Final-round cumulative values against the API's accumulated team feeds. Counting
# stats must match exactly; the API rounds rates to one decimal (percent), so the
# tolerance is a little above half a tenth. The API's turnovers_ratio,
# assists_ratio and free_throws_rate use other definitions and are not compared.
API_COUNTS = (("games_played", "traditional", "games_played"),
              ("points_for", "traditional", "points"),
              ("own_three_pointers_made", "traditional", "three_pointers_made"),
              ("own_free_throws_made", "traditional", "free_throws_made"),
              ("own_free_throws_attempted", "traditional", "free_throws_attempted"),
              ("own_offensive_rebounds", "traditional", "offensive_rebounds"),
              ("own_defensive_rebounds", "traditional", "defensive_rebounds"),
              ("own_turnovers", "traditional", "turnovers"),
              ("own_assists", "traditional", "assists"))
API_RATES = (("efg_pct", "advanced", "effective_field_goal_percentage"),
             ("true_shooting_pct", "advanced", "true_shooting_percentage"),
             ("orb_pct", "advanced", "offensive_rebounds_percentage"),
             ("drb_pct", "advanced", "defensive_rebounds_percentage"))
API_RATE_TOLERANCE = 0.06


def check_round_api_scope(cursor, competition_code, season_code):
    """Warnings where final-round team round totals differ from the API feeds (scopes without
    a feed are skipped). The totals are the in-memory source rows of app_standings_stats."""
    scope = (competition_code, season_code)
    final = {}
    for row in read_round_rows(cursor, *scope):  # sorted by scope, round and club
        final[(row["scope"], row["club_code"])] = row
    ours = list(final.values())
    api = {}
    for kind in ("traditional", "advanced"):
        cursor.execute(
            f'SELECT * FROM silver."season_team_stats_{kind}" WHERE competition_code = %s '
            "AND season_code = %s AND mode = 'accumulated'", scope)
        api[kind] = {(row["phase_code"], row["club_code"]): row for row in _dict_rows(cursor)}
    differences = {}
    for row in ours:
        key = (row["scope"], row["club_code"])
        for column, kind, source in API_COUNTS + API_RATES:
            theirs = api[kind].get(key)
            if theirs is None or theirs.get(source) is None or row[column] is None:
                continue
            scale = 100 if (column, kind, source) in API_RATES else 1
            gap = abs(float(row[column]) * scale - float(theirs[source]))
            if gap > (API_RATE_TOLERANCE if scale == 100 else 0):
                differences.setdefault((row["scope"], column), []).append(
                    f'{row["club_code"]}: {float(row[column]) * scale:g} vs API {float(theirs[source]):g}')
    return [f"team_round_stats {season_code} {scope_name}: {column} differs from the API "
            f"feed for {len(examples)} club(s) (e.g. {examples[0]})"
            for (scope_name, column), examples in sorted(differences.items())]


def check_round_rating_invariants(cursor, competition_code, season_code):
    """Errors where a connected scope-round's SRS sum or possession-weighted adjusted
    net sum is not zero (both hold by construction of the linear systems)."""
    cursor.execute('SELECT scope, round_number, connected, srs, adj_net_rating, possessions '
                   'FROM gold."app_standings_stats" WHERE competition_code = %s '
                   'AND season_code = %s', (competition_code, season_code))
    groups = {}
    for row in _dict_rows(cursor):
        if row["connected"]:
            groups.setdefault((row["scope"], row["round_number"]), []).append(row)
    issues = []
    for (scope_name, number), rows in sorted(groups.items()):
        srs_sum = sum(float(row["srs"]) for row in rows)
        weights = [float(row["possessions"] or 0) for row in rows]
        net_sum = sum(w * float(row["adj_net_rating"]) for w, row in zip(weights, rows))
        net_sum = net_sum / sum(weights) if sum(weights) else None
        if abs(srs_sum) > 1e-4:
            issues.append(f"gold.app_standings_stats {season_code} {scope_name} round {number}: "
                          f"srs sums to {srs_sum:g}, not 0")
        if net_sum is None or abs(net_sum) > 1e-4:
            issues.append(f"gold.app_standings_stats {season_code} {scope_name} round {number}: "
                          f"possession-weighted adj_net_rating averages {net_sum}, not 0")
    return issues


def check_round_player_rating_invariants(cursor, competition_code, season_code):
    """Errors where a scope round's seconds-weighted mean PER is not 15 (PER is normalized
    to 15 by construction; single low-minute players can legitimately go negative)."""
    cursor.execute('SELECT scope, round_number, person_key, seconds_played, per FROM '
                   'gold."app_player_round_ratings" WHERE competition_code = %s '
                   'AND season_code = %s', (competition_code, season_code))
    groups = {}
    for row in _dict_rows(cursor):
        if row["per"] is not None:
            groups.setdefault((row["scope"], row["round_number"]), []).append(row)
    issues = []
    for (scope_name, number), rows in sorted(groups.items()):
        seconds = sum(float(row["seconds_played"]) for row in rows)
        mean = sum(float(row["per"]) * float(row["seconds_played"]) for row in rows) / seconds
        prefix = f"gold.app_player_round_ratings {season_code} {scope_name} round {number}: "
        if abs(mean - 15) > 1e-4:
            issues.append(prefix + f"seconds-weighted mean per is {mean:g}, not 15")
    return issues


# Win Shares should add up to about one win per counted game (E2000-E2026: 0.90-1.07 of
# the games, tightest with many games). Rounds with few games are too noisy to judge.
WIN_SHARE_MIN_GAMES = 30
WIN_SHARE_TOLERANCE = 0.15


def check_round_win_share_totals(cursor, competition_code, season_code):
    """Warnings where a scope round's total Win Shares is far from its counted games."""
    scope = (competition_code, season_code)
    cursor.execute('SELECT scope, round_number, win_shares FROM gold."app_player_round_win_shares" '
                   'WHERE competition_code = %s AND season_code = %s', scope)
    totals = {}
    for row in _dict_rows(cursor):
        if row["win_shares"] is not None:
            key = (row["scope"], row["round_number"])
            totals[key] = totals.get(key, 0.0) + float(row["win_shares"])
    cursor.execute('SELECT scope, round_number, games_played FROM gold."app_standings_stats" '
                   'WHERE competition_code = %s AND season_code = %s', scope)
    games = {}
    for row in _dict_rows(cursor):
        key = (row["scope"], row["round_number"])
        games[key] = games.get(key, 0) + row["games_played"]
    warnings = []
    for key, total in sorted(totals.items()):
        counted = games.get(key, 0) / 2
        if counted >= WIN_SHARE_MIN_GAMES and abs(total / counted - 1) > WIN_SHARE_TOLERANCE:
            warnings.append(f"gold.app_player_round_win_shares {season_code} {key[0]} round "
                            f"{key[1]}: win shares total {total:.1f} for {counted:g} games")
    return warnings


def check_pbp_partition(cursor, name, competition_code, season_code):
    """Errors where a club's `all` scope is not the sum of its phase scopes for an additive
    column (holds by construction when the scopes group games correctly)."""
    columns = TEAM_PBP_ADDITIVE
    key = ("club_code",)
    cursor.execute(f'SELECT scope, {", ".join(key + columns)} FROM gold."{physical_name(name)}" '
                   'WHERE competition_code = %s AND season_code = %s',
                   (competition_code, season_code))
    whole, parts = {}, {}
    for row in _dict_rows(cursor):
        target = whole if row["scope"] == "all" else parts if row["scope"] != "PS" else None
        if target is None:
            continue
        ident = tuple(row[column] for column in key)
        entry = target.setdefault(ident, {column: 0 for column in columns})
        for column in columns:
            entry[column] += row[column] or 0
    issues = []
    for ident, entry in sorted(whole.items()):
        for column in columns:
            if parts.get(ident, {}).get(column, 0) != entry[column]:
                issues.append(f"gold.{physical_name(name)} {season_code} {ident}: {column} of the all scope "
                              "is not the sum of the phase scopes")
                break
    for ident in sorted(set(parts) - set(whole)):
        issues.append(f"gold.{physical_name(name)} {season_code} {ident}: phase rows without an all row")
    return issues


def check_on_off_totals(cursor, competition_code, season_code):
    """Errors where a club's on and off values do not add up to one team total per measure,
    or where its players' on-court seconds are not five times the team's seconds."""
    measures = ("seconds", "possessions_for", "possessions_against", "points_for",
                "points_against")
    columns = [f"{state}_{measure}" for state in ("on", "off") for measure in measures]
    cursor.execute(f'SELECT scope, club_code, person_key, {", ".join(columns)} '
                   'FROM gold."app_player_on_off" WHERE competition_code = %s '
                   'AND season_code = %s', (competition_code, season_code))
    totals, on_seconds, issues = {}, defaultdict(int), []
    for row in _dict_rows(cursor):
        ident = (row["scope"], row["club_code"])
        team = tuple(row[f"on_{m}"] + row[f"off_{m}"] for m in measures)
        if totals.setdefault(ident, team) != team:
            issues.append(f"gold.app_player_on_off {season_code} {ident}: on plus off differs "
                          f"between players (first seen at {row['person_key']})")
        on_seconds[ident] += row["on_seconds"]
    for ident, team in sorted(totals.items()):
        if on_seconds[ident] != 5 * team[0]:
            issues.append(f"gold.app_player_on_off {season_code} {ident}: on-court seconds are "
                          "not five times the team seconds")
    return issues


def check_lineup_totals(cursor, competition_code, season_code):
    """Errors where a club's lineup groups do not add up: per club and scope the 2-man and
    3-man rows each sum to ten times the 5-man rows for every summed column."""
    columns = ("seconds", "possessions_for", "possessions_against", "points_for",
               "points_against")
    cursor.execute(f'SELECT scope, club_code, lineup_size, {", ".join(columns)} '
                   'FROM gold."app_lineup_ratings" WHERE competition_code = %s '
                   'AND season_code = %s', (competition_code, season_code))
    sums = {}
    for row in _dict_rows(cursor):
        entry = sums.setdefault((row["scope"], row["club_code"]), {}).setdefault(
            row["lineup_size"], [0] * len(columns))
        for index, column in enumerate(columns):
            entry[index] += row[column] or 0
    issues = []
    for ident, sizes in sorted(sums.items()):
        for size in (2, 3):
            for index, column in enumerate(columns):
                if sizes.get(size, [0] * len(columns))[index] != 10 * sizes.get(
                        5, [0] * len(columns))[index]:
                    issues.append(f"gold.app_lineup_ratings {season_code} {ident}: {column} of the "
                                  f"{size}-man rows is not ten times the 5-man rows")
                    break
    return issues


def check_round_split_invariants(cursor, competition_code, season_code):
    """Errors where a row's splits disagree with its own cumulative totals."""
    cursor.execute('SELECT * FROM gold."app_standings_stats" WHERE competition_code = %s '
                   'AND season_code = %s', (competition_code, season_code))
    issues = []

    def problem(row, message):
        issues.append(f'gold.app_standings_stats {season_code} {row["scope"]} round '
                      f'{row["round_number"]} {row["club_code"]}: {message}')

    for row in _dict_rows(cursor):
        if row["home_games"] + row["away_games"] != row["games_played"]:
            problem(row, f'home + away games {row["home_games"] + row["away_games"]} '
                         f'!= games_played {row["games_played"]}')
        if row["home_wins"] + row["away_wins"] != row["wins"]:
            problem(row, f'home + away wins {row["home_wins"] + row["away_wins"]} '
                         f'!= wins {row["wins"]}')
        for size in WINDOWS:
            games = row[f"last{size}_games"]
            if games != min(size, row["games_played"]):
                problem(row, f"last{size}_games {games} is not min({size}, games_played)")
            elif row["games_played"] <= size and row[f"last{size}_mov"] != row["mov"]:
                problem(row, f"last{size}_mov differs from the cumulative mov")
    return issues


# Player final-round cumulative values against the API's accumulated player feeds.
# Counting stats and games must match exactly and minutes within rounding. Rates are
# compared only for players with at least 100 minutes: eFG% and TS% within the API's
# one-decimal rounding, rebound rates within 2 points (the API's team-minute
# conventions differ slightly). The API's turnovers_ratio, assists_ratio and
# possessions use other definitions and are not compared.
PLAYER_API_COUNTS = tuple((name, "traditional", name) for name in (
    "games_played", "points", "three_pointers_made", "free_throws_made",
    "free_throws_attempted", "offensive_rebounds", "defensive_rebounds", "total_rebounds",
    "assists", "steals", "turnovers", "blocks", "fouls_committed", "pir"))
PLAYER_API_RATES = (("efg_pct", "effective_field_goal_percentage", 0.06),
                    ("ts_pct", "true_shooting_percentage", 0.06),
                    ("orb_pct", "offensive_rebounds_percentage", 2.0),
                    ("drb_pct", "defensive_rebounds_percentage", 2.0),
                    ("trb_pct", "rebounds_percentage", 2.0))
PLAYER_RATE_MIN_SECONDS = 6000
PLAYER_MINUTES_TOLERANCE = 0.01


def check_round_player_api_scope(cursor, competition_code, season_code):
    """Warnings where player final-round rows differ from the API feeds."""
    scope = (competition_code, season_code)
    cursor.execute(
        'SELECT DISTINCT ON (scope, person_key) * FROM gold."app_player_round_stats" '
        'WHERE competition_code = %s AND season_code = %s '
        'ORDER BY scope, person_key, round_number DESC', scope)
    ours = _dict_rows(cursor)
    api = {}
    for kind in ("traditional", "advanced"):
        cursor.execute(
            f'SELECT * FROM silver."season_player_stats_{kind}" WHERE competition_code = %s '
            "AND season_code = %s AND mode = 'accumulated'", scope)
        api[kind] = {(row["phase_code"], row["person_key"]): row for row in _dict_rows(cursor)}
    differences = {}

    def note(row, metric, mine, theirs):
        differences.setdefault((row["scope"], metric), []).append(
            f'{row["person_key"]}: {mine:g} vs API {theirs:g}')

    for row in ours:
        key = (row["scope"], row["person_key"])
        traditional = api["traditional"].get(key)
        if traditional is not None:
            for column, _, source in PLAYER_API_COUNTS:
                if row[column] is not None and traditional.get(source) is not None                         and float(row[column]) != float(traditional[source]):
                    note(row, column, float(row[column]), float(traditional[source]))
            minutes = traditional.get("minutes_played")
            if row["seconds_played"] is not None and minutes is not None and abs(
                    float(row["seconds_played"]) / 60 - float(minutes)) > PLAYER_MINUTES_TOLERANCE:
                note(row, "minutes", float(row["seconds_played"]) / 60, float(minutes))
        advanced = api["advanced"].get(key)
        if advanced is not None and row["seconds_played"] is not None                 and float(row["seconds_played"]) >= PLAYER_RATE_MIN_SECONDS:
            for column, source, tolerance in PLAYER_API_RATES:
                if row[column] is not None and advanced.get(source) is not None                         and abs(float(row[column]) * 100 - float(advanced[source])) > tolerance:
                    note(row, column, float(row[column]) * 100, float(advanced[source]))
    return [f"gold.app_player_round_stats {season_code} {scope_name}: {metric} differs from the "
            f"API feed for {len(examples)} player(s) (e.g. {examples[0]})"
            for (scope_name, metric), examples in sorted(differences.items())]


# The cumulative round tables divide already rounded sums, so a player with a couple of
# minutes can differ from the exact single-game value by a few millionths.
TIE_TOLERANCE = 0.00001
PER_TOLERANCE = 0.0001
GAME_PLAYER_RATES = ("usage_pct", "assist_pct", "orb_pct", "drb_pct", "trb_pct", "steal_pct",
                     "block_pct", "tov_pct", "efg_pct", "true_shooting_pct",
                     "game_uper", "game_aper", "game_per")
# Shot and turnover ratios need no minutes; old box scores have 0-second lines with real stats.
SHOT_RATES = ("tov_pct", "efg_pct", "true_shooting_pct")


def _one(cursor, sql, params):
    cursor.execute(sql, params)
    return cursor.fetchall()


def check_game_advanced_ranges(cursor, competition_code, season_code):
    """Warnings for percent columns below 0 or above 2 (a few seconds of play can do it)."""
    warnings = []
    for column in GAME_PLAYER_RATES[:10]:
        count = _one(cursor, f'SELECT count(*) FROM gold."app_game_player_advanced" WHERE '
                     f'competition_code = %s AND season_code = %s AND ("{column}" < 0 '
                     f'OR "{column}" > 2)', (competition_code, season_code))[0][0]
        if count:
            warnings.append(f"gold.app_game_player_advanced {season_code}: {count} rows have "
                            f"{column} below 0 or above 2")
    return warnings


def check_game_advanced_invariants(cursor, name, competition_code, season_code):
    """Row shape, null handling, league-mean PER and round-1 ties for the 30h tables."""
    scope = (competition_code, season_code)
    prefix = f"gold.{physical_name(name)} {season_code}: "
    issues = []
    if name == "game_team_advanced":
        for code, rows, distinct in _one(
                cursor, 'SELECT game_code, count(*), count(DISTINCT possessions) FROM '
                'gold."app_game_team_advanced" WHERE competition_code = %s AND season_code = %s '
                'GROUP BY game_code HAVING count(*) <> 2 OR count(DISTINCT possessions) > 1',
                scope):
            issues.append(prefix + f"game {code} has {rows} rows and {distinct} possession values")
        for tie in ("possessions", "pace", "offensive_rating", "defensive_rating"):
            bad = _one(cursor,
                       f'SELECT count(*) FROM gold."app_game_team_advanced" a JOIN gold."app_games" g '
                       'USING (competition_code, season_code, game_code) '
                       'JOIN gold."app_standings_stats" t ON t.competition_code = a.competition_code '
                       "AND t.season_code = a.season_code AND t.scope = 'all' AND t.round_number = 1 "
                       'AND t.club_code = a.club_code AND t.games_played = 1 '
                       f'WHERE a.competition_code = %s AND a.season_code = %s AND g.round_number = 1 '
                       f'AND abs(a."{tie}" - t."{tie}") > {TIE_TOLERANCE}', scope)[0][0]
            if bad:
                issues.append(prefix + f"{bad} round-1 rows differ from app_standings_stats.{tie}")
        return issues
    missing = _one(
        cursor, 'SELECT count(*) FROM (SELECT game_code, side, person_key FROM gold."app_game_player_stats" '
        'WHERE competition_code = %s AND season_code = %s AND game_code IN (SELECT game_code FROM '
        'gold."app_game_team_advanced" WHERE competition_code = %s AND season_code = %s) '
        'EXCEPT SELECT game_code, side, person_key FROM gold."app_game_player_advanced" '
        'WHERE competition_code = %s AND season_code = %s) d', scope * 3)[0][0]
    extra = _one(
        cursor, 'SELECT count(*) FROM (SELECT game_code, side, person_key FROM gold."app_game_player_advanced" '
        'WHERE competition_code = %s AND season_code = %s EXCEPT SELECT game_code, side, person_key '
        'FROM gold."app_game_player_stats" WHERE competition_code = %s AND season_code = %s) d',
        scope * 2)[0][0]
    if missing or extra:
        issues.append(prefix + f"{missing} box-score rows missing, {extra} not in game_player_stats")
    for column in (c for c in GAME_PLAYER_RATES if c not in SHOT_RATES):
        bad = _one(cursor, f'SELECT count(*) FROM gold."app_game_player_advanced" WHERE '
                   'competition_code = %s AND season_code = %s AND (seconds_played IS NULL '
                   f'OR seconds_played = 0) AND "{column}" IS NOT NULL', scope)[0][0]
        if bad:
            issues.append(prefix + f"{bad} zero-minute rows have a {column} value")
    # game_per = game_aper * 15 / A, where A is the seconds-weighted mean game_aper of every
    # line of the phase round, including the lines under the floor whose game_per is NULL.
    groups = _one(cursor,
                  'SELECT g.phase_code, g.round_number, count(*) FILTER (WHERE a.game_per IS NOT '
                  f'NULL AND abs(a.game_per - a.game_aper * 15 / m.mean) > {PER_TOLERANCE}) FROM '
                  'gold."app_game_player_advanced" a JOIN gold."app_games" g USING (competition_code, '
                  'season_code, game_code) JOIN (SELECT g2.phase_code, g2.round_number, '
                  'sum(a2.game_aper * a2.seconds_played) / sum(a2.seconds_played) AS mean '
                  'FROM gold."app_game_player_advanced" a2 JOIN gold."app_games" g2 USING '
                  '(competition_code, season_code, game_code) WHERE a2.competition_code = %s '
                  'AND a2.season_code = %s AND a2.game_aper IS NOT NULL AND a2.seconds_played > 0 '
                  'GROUP BY g2.phase_code, g2.round_number) m ON m.phase_code = g.phase_code '
                  'AND m.round_number = g.round_number WHERE a.competition_code = %s '
                  'AND a.season_code = %s GROUP BY g.phase_code, g.round_number', scope * 2)
    for phase, number, bad in groups:
        if bad:
            issues.append(prefix + f"{phase} round {number}: {bad} game_per values are not "
                          "game_aper scaled to a seconds-weighted mean of 15")
    short = _one(cursor, 'SELECT count(*) FROM gold."app_game_player_advanced" WHERE '
                 'competition_code = %s AND season_code = %s AND game_per IS NOT NULL '
                 f'AND seconds_played < {PER_FLOOR_SECONDS}', scope)[0][0]
    if short:
        issues.append(prefix + f"{short} rows under {PER_FLOOR_SECONDS} seconds have a game_per")
    # Usage only ties where Silver kept the box-score estimate (no on-court counts).
    estimate_only = ('JOIN silver."game_player_advanced" s USING (competition_code, season_code, '
                     "game_code, side, person_key) ", " AND s.rate_source = 'estimate'")
    ties = (("usage_pct", "player_round_stats", "all", "usg_pct", estimate_only),
            ("true_shooting_pct", "player_round_stats", "all", "ts_pct", ("", "")),
            ("efg_pct", "player_round_stats", "all", "efg_pct", ("", "")),
            ("game_score", "player_round_stats", "all", "game_score_total", ("", "")),
            ("game_per", "player_round_ratings", "RS", "per", ("", "")))
    for column, table, round_scope, other, (join, condition) in ties:
        extra_filter = " AND t.games_played = 1" if table == "player_round_stats" else ""
        bad = _one(cursor,
                   f'SELECT count(*) FROM gold."app_game_player_advanced" a JOIN gold."app_games" g '
                   f'USING (competition_code, season_code, game_code) {join}'
                   f'JOIN gold."{physical_name(table)}" t ON t.competition_code = a.competition_code '
                   "AND t.season_code = a.season_code AND t.round_number = 1 "
                   f"AND t.scope = '{round_scope}' AND t.person_key = a.person_key "
                   f"AND t.club_code = a.club_code{extra_filter} "
                   'WHERE a.competition_code = %s AND a.season_code = %s AND g.round_number = 1 '
                   f'AND abs(a."{column}" - t."{other}") > {TIE_TOLERANCE}{condition}',
                   scope)[0][0]
        if bad:
            issues.append(prefix + f"{bad} round-1 rows differ from {table}.{other}")
    return issues
