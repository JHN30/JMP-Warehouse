"""The 16 source projections owned by the first Gold build."""

from postgres_etl.flat_schema import (COLUMN_NAMES, Field, SCOPE,
                                       STANDINGS_IDENTITY, TABLES as SILVER_TABLES,
                                       Table, snake)


SOURCE_NAMES = (
    "seasons", "clubs", "people", "registrations", "rounds", "games",
    "game_officials", "game_period_scores", "game_player_stats",
    "game_team_stats", "season_player_stats_traditional",
    "season_player_stats_advanced", "season_player_stats_scoring",
    "season_player_stats_misc", "play_by_play", "shots",
)
PLAYER_STATS = frozenset(name for name in SOURCE_NAMES
                         if name.startswith("season_player_stats_"))
TABLES = {name: SILVER_TABLES[name] for name in SOURCE_NAMES}

STANDINGS_FEEDS = (
    ("standings_basic", "basic"), ("standings_calendar", "calendar"),
    ("standings_streaks", "streaks"),
    ("standings_ahead_behind", "ahead_behind"),
    ("standings_margins", "margins"),
)
STANDINGS_CHILDREN = ("standings_basic_form", "standings_calendar_streaks")
STANDINGS_SHARED = ("position", "position_change", "games_played",
                    "games_won", "games_lost", "qualified")
STANDINGS_RENAMES = {
    "longest_loss_streak_current_season": "longest_lose_streak_current_season",
    "longest_loss_streak_any_season": "longest_lose_streak_any_season",
}


def feed_fields(name):
    """The six shared page fields plus metrics unique to this Silver feed."""
    identity_names = {field.name for field in SCOPE + STANDINGS_IDENTITY}
    metrics = tuple(field for field in SILVER_TABLES[name].fields
                    if field.name not in identity_names)
    shared = tuple(field for field in STANDINGS_IDENTITY
                   if field.name in STANDINGS_SHARED)
    return shared + metrics


STANDINGS_FIELDS = SCOPE + (
    Field("phase_code", "TEXT NOT NULL", "standings_basic.phase_code"),
    Field("round_number", "INTEGER NOT NULL", "standings_basic.round_number"),
    Field("club_code", "TEXT NOT NULL", "standings_basic.club_code"),
    Field("club_name", "TEXT", "standings_basic.club_name"),
    Field("club_tv_code", "TEXT", "standings_basic.club_tv_code"),
    Field("crest_url", "TEXT", "clubs.crest_url"),
    Field("group_name", "TEXT", "standings_basic.group_name"),
) + tuple(
    Field(f'{prefix}_{STANDINGS_RENAMES.get(field.name, field.name)}', field.kind,
          f'{name}.{field.name}')
    for name, prefix in STANDINGS_FEEDS for field in feed_fields(name)
) + (
    Field("form", "JSONB NOT NULL", "standings_basic_form"),
    Field("streak_history", "JSONB NOT NULL", "standings_calendar_streaks"),
)
STANDINGS_TABLE = Table(
    "standings_page",
    ("competition_code", "season_code", "phase_code", "round_number", "club_code"),
    STANDINGS_FIELDS,
)
TEAM_MEASURES = (
    "points", "fieldGoalsMade2", "fieldGoalsAttempted2", "fieldGoalsMade3",
    "fieldGoalsAttempted3", "freeThrowsMade", "freeThrowsAttempted",
    "fieldGoalsMadeTotal", "fieldGoalsAttemptedTotal", "totalRebounds",
    "defensiveRebounds", "offensiveRebounds", "assistances", "steals",
    "turnovers", "blocksFavour", "blocksAgainst", "foulsCommited",
    "foulsReceived", "valuation",
)
TEAM_MEASURE_COLUMNS = tuple((snake(name), COLUMN_NAMES.get(snake(name), snake(name)))
                             for name in TEAM_MEASURES)
TEAM_FIELDS = SCOPE + (
    Field("phase_code", "TEXT NOT NULL", "games.phase_code"),
    Field("club_code", "TEXT NOT NULL", "games.club_code"),
    Field("club_name", "TEXT", "clubs.name"),
    Field("games_played", "INTEGER NOT NULL", "game_team_stats"),
) + tuple(Field(f"{side}_{name}", "NUMERIC", f"game_team_stats.{source}")
          for side in ("own", "opp") for name, source in TEAM_MEASURE_COLUMNS)
TEAM_SEASON_TABLE = Table(
    "team_season_stats", ("competition_code", "season_code", "phase_code", "club_code"),
    TEAM_FIELDS,
)
COVERAGE_SEASON_TABLE = Table(
    "coverage_seasons", ("competition_code", "season_code"),
    SCOPE + (Field("items", "JSONB NOT NULL", "silver"),),
)
COVERAGE_GAME_TABLE = Table(
    "coverage_games", ("competition_code", "season_code", "game_code"),
    SCOPE + (Field("game_code", "INTEGER NOT NULL", "games.game_code"),
             Field("items", "JSONB NOT NULL", "silver")),
)
RECORDS_KEY = ("competition_code", "metric", "rank_ordinal")
RECORDS_BASE = (
    Field("competition_code", "TEXT NOT NULL", "silver"),
    Field("metric", "TEXT NOT NULL", "silver"),
    Field("rank_ordinal", "INTEGER NOT NULL", "silver"),
    Field("season_code", "TEXT NOT NULL", "silver"),
)
RECORDS_TABLES = {
    "app_records_player_seasons": Table("records_player_seasons", RECORDS_KEY,
        RECORDS_BASE + (
            Field("person_key", "TEXT NOT NULL", "season_player_stats_traditional"),
            Field("player_name", "TEXT", "season_player_stats_traditional"),
            Field("club_code", "TEXT", "season_player_stats_traditional"),
            Field("club_name", "TEXT", "season_player_stats_traditional"),
            Field("value", "NUMERIC NOT NULL", "season_player_stats_traditional"),
        )),
    "app_records_single_games": Table("records_single_games", RECORDS_KEY,
        RECORDS_BASE + (
            Field("game_code", "INTEGER NOT NULL", "game_player_stats"),
            Field("scheduled_at", "TIMESTAMPTZ", "games"),
            Field("person_key", "TEXT NOT NULL", "game_player_stats"),
            Field("player_name", "TEXT", "game_player_stats"),
            Field("club_code", "TEXT", "game_player_stats"),
            Field("club_name", "TEXT", "game_player_stats"),
            Field("value", "NUMERIC NOT NULL", "game_player_stats"),
        )),
    "app_records_team_seasons": Table("records_team_seasons", RECORDS_KEY,
        RECORDS_BASE + (
            Field("club_code", "TEXT NOT NULL", "games"),
            Field("club_name", "TEXT", "games"),
            Field("value", "NUMERIC NOT NULL", "game_team_stats"),
        )),
}
SERIES_TABLE = Table("postseason_series",
    ("competition_code", "season_code", "phase_code", "club_a_code", "club_b_code"),
    SCOPE + (
        Field("phase_code", "TEXT NOT NULL", "games"),
        Field("club_a_code", "TEXT NOT NULL", "games"),
        Field("club_b_code", "TEXT NOT NULL", "games"),
        Field("club_a_name", "TEXT", "games"),
        Field("club_b_name", "TEXT", "games"),
        Field("games_played", "INTEGER NOT NULL", "games"),
        Field("club_a_wins", "INTEGER NOT NULL", "games"),
        Field("club_b_wins", "INTEGER NOT NULL", "games"),
        Field("winner_club_code", "TEXT", "games"),
        Field("games", "JSONB NOT NULL", "games"),
    ),
)
IDENTITY_TABLES = {
    "app_players": Table("players", ("competition_code", "person_code"), (
        Field("competition_code", "TEXT NOT NULL", "silver"),
        Field("person_code", "TEXT NOT NULL", "people"),
        Field("name", "TEXT", "people"),
        Field("country_code", "TEXT", "people"),
        Field("country_name", "TEXT", "people"),
        Field("height_cm", "INTEGER", "people"),
        Field("weight_kg", "INTEGER", "people"),
        Field("birth_at", "TIMESTAMP", "people"),
        Field("birth_country_code", "TEXT", "people"),
        Field("birth_country_name", "TEXT", "people"),
        Field("position", "INTEGER", "registrations"),
        Field("position_name", "TEXT", "registrations"),
        Field("first_season_code", "TEXT NOT NULL", "registrations"),
        Field("last_season_code", "TEXT NOT NULL", "registrations"),
        Field("seasons_played", "INTEGER NOT NULL", "registrations"),
        Field("clubs", "JSONB NOT NULL", "registrations"),
    )),
    "app_club_identities": Table("club_identities", ("competition_code", "club_code"), (
        Field("competition_code", "TEXT NOT NULL", "silver"),
        Field("club_code", "TEXT NOT NULL", "clubs"),
        Field("name", "TEXT", "clubs"),
        Field("crest_url", "TEXT", "clubs"),
        Field("country_code", "TEXT", "clubs"),
        Field("country_name", "TEXT", "clubs"),
        Field("first_season_code", "TEXT NOT NULL", "clubs"),
        Field("last_season_code", "TEXT NOT NULL", "clubs"),
        Field("seasons_played", "INTEGER NOT NULL", "clubs"),
    )),
}
AGGREGATE_NAMES = ("app_team_season_stats", "app_coverage_seasons",
                   "app_coverage_games")
# The Gold tables of features 26-29: excluded from DERIVED_NAMES, added to the Neon
# allowlist in neon_publish/contract.py as NEW_TABLES (feature 30g).
ROUND_MEASURES = (
    "field_goals_made", "field_goals_attempted", "three_pointers_made",
    "free_throws_made", "free_throws_attempted", "offensive_rebounds",
    "defensive_rebounds", "turnovers", "assists",
)
ROUND_NAMES = ("team_round_stats", "team_round_ratings", "team_round_splits",
               "player_round_stats", "player_round_ratings", "player_round_win_shares",
               "app_standings_stats", "team_pbp_stats", "team_shot_zone_stats",
               "player_on_off", "lineup_ratings", "player_rapm")
PBP_NAMES = ("team_pbp_stats", "team_shot_zone_stats")
WINDOWS = (5, 10)
SPLIT_GROUPS = ("home", "away", *(f"last{size}" for size in WINDOWS))
SPLIT_MEASURES = ("mov", "offensive_rating", "defensive_rating", "net_rating", "pace")
# Feature 30h: per-game advanced tables, published to Neon as app_game_*_advanced.
GAME_ADVANCED_NAMES = ("game_player_advanced", "game_team_advanced")
SEASON_DERIVED_NAMES = AGGREGATE_NAMES + ROUND_NAMES + GAME_ADVANCED_NAMES
TEAM_ROUND_TABLE = Table(
    "team_round_stats",
    ("competition_code", "season_code", "scope", "round_number", "club_code"),
    SCOPE + (
        Field("scope", "TEXT NOT NULL", "games.phase_code"),
        Field("round_number", "INTEGER NOT NULL", "games.round_number"),
        Field("club_code", "TEXT NOT NULL", "games.club_code"),
        Field("club_name", "TEXT", "clubs.name"),
        Field("games_played", "INTEGER NOT NULL", "game_team_advanced"),
        Field("wins", "INTEGER NOT NULL", "games.match_winner_club_code"),
        Field("losses", "INTEGER NOT NULL", "games.match_winner_club_code"),
        Field("points_for", "NUMERIC", "game_team_stats.points"),
        Field("points_against", "NUMERIC", "game_team_stats.points"),
    ) + tuple(Field(f"{side}_{name}", "NUMERIC", f"game_team_stats.{name}")
              for side in ("own", "opp") for name in ROUND_MEASURES) + tuple(
        Field(name, "NUMERIC", "game_team_advanced" if name in (
            "game_minutes", "possessions") else "derived")
        for name in (
            "game_minutes", "possessions", "mov", "pythagorean_exponent",
            "pythagorean_win_pct", "pythagorean_wins", "pace", "offensive_rating",
            "defensive_rating", "net_rating", "efg_pct", "tov_pct", "orb_pct",
            "drb_pct", "ft_rate", "opp_efg_pct", "opp_tov_pct", "opp_ft_rate",
            "true_shooting_pct", "assist_ratio")),
)
TEAM_RATINGS_TABLE = Table(
    "team_round_ratings",
    ("competition_code", "season_code", "scope", "round_number", "club_code"),
    SCOPE + (
        Field("scope", "TEXT NOT NULL", "games.phase_code"),
        Field("round_number", "INTEGER NOT NULL", "games.round_number"),
        Field("club_code", "TEXT NOT NULL", "games.club_code"),
        Field("connected", "BOOLEAN NOT NULL", "derived"),
    ) + tuple(Field(name, "NUMERIC", "derived") for name in (
        "league_offensive_rating", "league_pace", "relative_offensive_rating",
        "relative_defensive_rating", "relative_pace", "srs", "sos", "sov",
        "adj_offensive_rating", "adj_defensive_rating", "adj_net_rating")),
)

TEAM_SPLITS_TABLE = Table(
    "team_round_splits",
    ("competition_code", "season_code", "scope", "round_number", "club_code"),
    SCOPE + (
        Field("scope", "TEXT NOT NULL", "games.phase_code"),
        Field("round_number", "INTEGER NOT NULL", "games.round_number"),
        Field("club_code", "TEXT NOT NULL", "games.club_code"),
    ) + tuple(field for group in SPLIT_GROUPS for field in (
        Field(f"{group}_games", "INTEGER NOT NULL", "games"),
        Field(f"{group}_wins", "INTEGER NOT NULL", "games.match_winner_club_code"),
    ) + tuple(Field(f"{group}_{name}", "NUMERIC", "derived") for name in SPLIT_MEASURES)),
)

PLAYER_TOTALS = (
    "seconds_played", "points", "field_goals_made", "field_goals_attempted",
    "three_pointers_made", "three_pointers_attempted", "free_throws_made",
    "free_throws_attempted", "offensive_rebounds", "defensive_rebounds",
    "total_rebounds", "assists", "steals", "turnovers", "blocks", "fouls_committed", "pir",
)
PLAYER_RATES = (
    "ts_pct", "efg_pct", "usg_pct", "ast_pct", "orb_pct", "drb_pct", "trb_pct",
    "stl_pct", "blk_pct", "tov_pct", "possessions_played", "points_per_100",
    "rebounds_per_100", "assists_per_100", "steals_per_100", "blocks_per_100",
    "turnovers_per_100", "game_score_total", "game_score_average", "pie",
)
PLAYER_ROUND_TABLE = Table(
    "player_round_stats",
    ("competition_code", "season_code", "scope", "round_number", "person_key"),
    SCOPE + (
        Field("scope", "TEXT NOT NULL", "games.phase_code"),
        Field("round_number", "INTEGER NOT NULL", "games.round_number"),
        Field("person_key", "TEXT NOT NULL", "game_player_stats.person_key"),
        Field("club_code", "TEXT", "game_player_stats.club_code"),
        Field("player_name", "TEXT", "game_player_stats.person_name"),
        Field("games_played", "INTEGER NOT NULL", "game_player_stats"),
        Field("games_started", "INTEGER NOT NULL", "game_player_stats.started"),
    ) + tuple(Field(name, "NUMERIC", f"game_player_stats.{name}") for name in PLAYER_TOTALS)
      + tuple(Field(name, "NUMERIC", "derived") for name in PLAYER_RATES),
)

PLAYER_RATINGS_TABLE = Table(
    "player_round_ratings",
    ("competition_code", "season_code", "scope", "round_number", "person_key"),
    SCOPE + (
        Field("scope", "TEXT NOT NULL", "games.phase_code"),
        Field("round_number", "INTEGER NOT NULL", "games.round_number"),
        Field("person_key", "TEXT NOT NULL", "game_player_stats.person_key"),
        Field("club_code", "TEXT", "game_player_stats.club_code"),
        Field("player_name", "TEXT", "game_player_stats.person_name"),
        Field("games_played", "INTEGER NOT NULL", "game_player_stats"),
        Field("seconds_played", "NUMERIC", "game_player_stats.seconds_played"),
    ) + tuple(Field(name, "NUMERIC", "derived") for name in ("uper", "aper", "per")),
)

PLAYER_WIN_SHARES_TABLE = Table(
    "player_round_win_shares",
    ("competition_code", "season_code", "scope", "round_number", "person_key"),
    SCOPE + (
        Field("scope", "TEXT NOT NULL", "games.phase_code"),
        Field("round_number", "INTEGER NOT NULL", "games.round_number"),
        Field("person_key", "TEXT NOT NULL", "game_player_stats.person_key"),
        Field("club_code", "TEXT", "game_player_stats.club_code"),
        Field("player_name", "TEXT", "game_player_stats.person_name"),
        Field("games_played", "INTEGER NOT NULL", "game_player_stats"),
        Field("seconds_played", "NUMERIC", "game_player_stats.seconds_played"),
    ) + tuple(Field(name, "NUMERIC", "derived") for name in (
        "off_win_shares", "def_win_shares", "win_shares", "win_shares_per_48")),
)

# app_standings_stats projects the three team round tables (no new formulas); its final
# Neon name is app_standings_stats.
STANDINGS_STATS_SOURCES = (
    ("team_round_stats", TEAM_ROUND_TABLE, (
        "club_name", "games_played", "wins", "losses", "points_for", "points_against",
        "possessions", "mov", "pythagorean_win_pct", "pythagorean_wins", "pace",
        "offensive_rating", "defensive_rating", "net_rating", "efg_pct", "tov_pct",
        "orb_pct", "drb_pct", "ft_rate", "opp_efg_pct", "opp_tov_pct", "opp_ft_rate",
        "true_shooting_pct", "assist_ratio")),
    ("team_round_ratings", TEAM_RATINGS_TABLE, (
        "connected", "league_offensive_rating", "league_pace", "relative_offensive_rating",
        "relative_defensive_rating", "relative_pace", "srs", "sos", "sov",
        "adj_offensive_rating", "adj_defensive_rating", "adj_net_rating")),
    ("team_round_splits", TEAM_SPLITS_TABLE, tuple(
        f"{group}_{name}" for group in SPLIT_GROUPS
        for name in ("games", "wins", *SPLIT_MEASURES))),
)
STANDINGS_STATS_TABLE = Table(
    "app_standings_stats",
    ("competition_code", "season_code", "scope", "round_number", "club_code"),
    SCOPE + (
        Field("scope", "TEXT NOT NULL", "games.phase_code"),
        Field("round_number", "INTEGER NOT NULL", "games.round_number"),
        Field("club_code", "TEXT NOT NULL", "games.club_code"),
    ) + tuple(next(field for field in source.fields if field.name == name)
              for _, source, names in STANDINGS_STATS_SOURCES for name in names),
)

# Play-by-play aggregates (feature 19d): per club and scope from the Silver tables of 19a-19c.
TEAM_PBP_INTEGERS = ("games", "timed_games", "runs_6_plus", "clutch_games", "flagged_games",
                     "field_goals_made", "assisted_field_goals")
TEAM_PBP_ADDITIVE = (
    "games", "counted_possessions", "estimated_possessions", "possession_seconds",
    "timed_games", "time_leading_seconds", "time_trailing_seconds", "time_tied_seconds",
    "runs_6_plus", "clutch_games", "clutch_seconds", "clutch_points_for",
    "clutch_points_against", "flagged_games", "fast_break_points", "second_chance_points",
    "points_off_turnover_points", "field_goals_made", "assisted_field_goals")
TEAM_PBP_COLUMNS = TEAM_PBP_ADDITIVE + (
    "avg_possession_seconds", "lead_changes_per_game", "ties_per_game", "largest_lead",
    "longest_run", "assisted_fg_pct")
TEAM_PBP_TABLE = Table(
    "team_pbp_stats",
    ("competition_code", "season_code", "scope", "club_code"),
    SCOPE + (
        Field("scope", "TEXT NOT NULL", "games.phase_code"),
        Field("club_code", "TEXT NOT NULL", "game_team_possessions.club_code"),
    ) + tuple(Field(name, "INTEGER" if name in TEAM_PBP_INTEGERS else "NUMERIC", "derived")
              for name in TEAM_PBP_COLUMNS),
)
ZONE_ADDITIVE = ("attempts", "made", "points")
TEAM_ZONE_TABLE = Table(
    "team_shot_zone_stats",
    ("competition_code", "season_code", "scope", "club_code", "zone"),
    SCOPE + (
        Field("scope", "TEXT NOT NULL", "games.phase_code"),
        Field("club_code", "TEXT NOT NULL", "game_team_shot_zones.club_code"),
        Field("zone", "TEXT NOT NULL", "game_team_shot_zones.zone"),
    ) + tuple(Field(name, "INTEGER", "game_team_shot_zones") for name in ZONE_ADDITIVE)
      + tuple(Field(name, "NUMERIC", "derived") for name in ("fg_pct", "attempt_share")),
)

# Player on/off (feature 29b): per club and scope from the lineup stints of 29b.
ON_OFF_ADDITIVE = tuple(f"{state}_{column}" for state in ("on", "off") for column in (
    "seconds", "possessions_for", "possessions_against", "points_for", "points_against"))
ON_OFF_RATINGS = ("on_ortg", "on_drtg", "on_net_rating", "off_ortg", "off_drtg",
                  "off_net_rating", "ortg_diff", "drtg_diff", "net_rating_diff")
PLAYER_ON_OFF_TABLE = Table(
    "player_on_off",
    ("competition_code", "season_code", "scope", "club_code", "person_key"),
    SCOPE + (
        Field("scope", "TEXT NOT NULL", "games.phase_code"),
        Field("club_code", "TEXT NOT NULL", "game_team_lineup_stints.club_code"),
        Field("person_key", "TEXT NOT NULL", "game_team_lineup_stints.players"),
        Field("player_name", "TEXT", "game_player_stats.person_name"),
        Field("games", "INTEGER NOT NULL", "game_team_lineup_stints"),
    ) + tuple(Field(name, "INTEGER", "game_team_lineup_stints") for name in ON_OFF_ADDITIVE)
      + tuple(Field(name, "NUMERIC", "derived") for name in ON_OFF_RATINGS),
)

# Lineup ratings (feature 29c): 2, 3 and 5-man groups per club and scope from the same stints.
LINEUP_MEASURES = ("seconds", "possessions_for", "possessions_against", "points_for",
                   "points_against")
LINEUP_SIZES = (2, 3, 5)
LINEUP_RATINGS_TABLE = Table(
    "lineup_ratings",
    ("competition_code", "season_code", "scope", "club_code", "lineup_size", "lineup"),
    SCOPE + (
        Field("scope", "TEXT NOT NULL", "games.phase_code"),
        Field("club_code", "TEXT NOT NULL", "game_team_lineup_stints.club_code"),
        Field("lineup_size", "INTEGER NOT NULL", "derived"),
        Field("lineup", "TEXT NOT NULL", "game_team_lineup_stints.players"),
        Field("lineup_names", "TEXT", "game_player_stats.person_name"),
        Field("games", "INTEGER NOT NULL", "game_team_lineup_stints"),
    ) + tuple(Field(name, "INTEGER", "game_team_lineup_stints") for name in LINEUP_MEASURES)
      + tuple(Field(name, "NUMERIC", "derived") for name in ("ortg", "drtg", "net_rating")),
)

# RAPM (feature 29d): one row per player and season from a ridge fit over the lineup stints.
PLAYER_RAPM_TABLE = Table(
    "player_rapm",
    ("competition_code", "season_code", "scope", "person_key"),
    SCOPE + (
        Field("scope", "TEXT NOT NULL", "derived"),
        Field("person_key", "TEXT NOT NULL", "game_team_lineup_stints.players"),
        Field("player_name", "TEXT", "game_player_stats.person_name"),
        Field("seconds", "INTEGER", "game_team_lineup_stints"),
        Field("possessions_offense", "INTEGER", "game_team_lineup_stints"),
        Field("possessions_defense", "INTEGER", "game_team_lineup_stints"),
    ) + tuple(Field(name, "NUMERIC", "derived")
              for name in ("penalty", "offense", "defense", "rapm")),
)

GAME_PLAYER_MEASURES = (
    "game_score", "usage_pct", "assist_pct", "orb_pct", "drb_pct", "trb_pct",
    "steal_pct", "block_pct", "tov_pct", "efg_pct", "true_shooting_pct",
    "game_uper", "game_aper", "game_per",
)
GAME_PLAYER_ADVANCED_TABLE = Table(
    "game_player_advanced",
    ("competition_code", "season_code", "game_code", "side", "person_key"),
    SCOPE + (
        Field("game_code", "INTEGER NOT NULL", "game_player_advanced.game_code"),
        Field("side", "TEXT NOT NULL", "game_player_advanced.side"),
        Field("person_key", "TEXT NOT NULL", "game_player_advanced.person_key"),
        Field("club_code", "TEXT NOT NULL", "game_player_advanced.club_code"),
        Field("seconds_played", "NUMERIC", "game_player_advanced.seconds_played"),
    ) + tuple(Field(name, "NUMERIC", "derived" if name in ("game_uper", "game_aper", "game_per")
                    else "game_player_advanced")
              for name in GAME_PLAYER_MEASURES),
)
GAME_TEAM_MEASURES = (
    "game_minutes", "own_possessions_estimate", "possessions", "pace", "offensive_rating",
    "defensive_rating", "net_rating", "efg_pct", "opp_efg_pct", "tov_pct", "opp_tov_pct",
    "orb_pct", "drb_pct", "ft_rate", "opp_ft_rate", "true_shooting_pct", "assist_ratio",
)
GAME_TEAM_ADVANCED_TABLE = Table(
    "game_team_advanced",
    ("competition_code", "season_code", "game_code", "side"),
    SCOPE + (
        Field("game_code", "INTEGER NOT NULL", "game_team_advanced.game_code"),
        Field("side", "TEXT NOT NULL", "game_team_advanced.side"),
        Field("club_code", "TEXT NOT NULL", "game_team_advanced.club_code"),
    ) + tuple(Field(name, "NUMERIC", "game_team_advanced") for name in GAME_TEAM_MEASURES),
)

DERIVED_NAMES = ("app_standings", *AGGREGATE_NAMES,
                 *RECORDS_TABLES, "app_postseason_series", *IDENTITY_TABLES)
GOLD_TABLES = {**TABLES, "app_standings": STANDINGS_TABLE,
               "app_team_season_stats": TEAM_SEASON_TABLE,
               "app_coverage_seasons": COVERAGE_SEASON_TABLE,
               "app_coverage_games": COVERAGE_GAME_TABLE,
               **RECORDS_TABLES, "app_postseason_series": SERIES_TABLE,
               **IDENTITY_TABLES, "team_round_stats": TEAM_ROUND_TABLE,
               "team_round_ratings": TEAM_RATINGS_TABLE,
               "team_round_splits": TEAM_SPLITS_TABLE,
               "player_round_stats": PLAYER_ROUND_TABLE,
               "player_round_ratings": PLAYER_RATINGS_TABLE,
               "player_round_win_shares": PLAYER_WIN_SHARES_TABLE,
               "app_standings_stats": STANDINGS_STATS_TABLE,
               "team_pbp_stats": TEAM_PBP_TABLE, "team_shot_zone_stats": TEAM_ZONE_TABLE,
               "player_on_off": PLAYER_ON_OFF_TABLE,
               "lineup_ratings": LINEUP_RATINGS_TABLE,
               "player_rapm": PLAYER_RAPM_TABLE,
               "game_player_advanced": GAME_PLAYER_ADVANCED_TABLE,
               "game_team_advanced": GAME_TEAM_ADVANCED_TABLE}


def columns(name):
    return tuple(field.name for field in GOLD_TABLES[name].fields)


def create_table_sql(name):
    spec = GOLD_TABLES[name]
    fields = ", ".join(f'"{field.name}" {field.kind}' for field in spec.fields)
    key = ", ".join(f'"{column}"' for column in spec.key)
    return f'CREATE TABLE IF NOT EXISTS gold."{name}" ({fields}, PRIMARY KEY ({key}))'


def scope_predicate(name, alias=None):
    prefix = f'{alias}.' if alias else ""
    predicate = (f'{prefix}"competition_code" = %s AND '
                 f'{prefix}"season_code" = %s')
    if name in PLAYER_STATS:
        predicate += f' AND {prefix}"phase_code" <> \'PS\''
    return predicate


def count_sql(name, schema):
    if schema not in {"silver", "gold"}:
        raise ValueError(f"Unknown schema: {schema}")
    return f'SELECT count(*) FROM {schema}."{name}" WHERE {scope_predicate(name)}'
