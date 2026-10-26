"""Top-50 all-time record rows derived from the complete Silver history."""

from gold_etl.schema import RECORDS_TABLES, columns
from gold_etl.standings import _dict_rows


METRICS = {
    "app_records_player_seasons": (("points_scored", "points"),
                                   ("total_rebounds", "total_rebounds"),
                                   ("assists", "assists"), ("pir", "pir")),
    "app_records_single_games": (("points", "points"), ("valuation", "pir"),
                                 ("total_rebounds", "total_rebounds"),
                                 ("assistances", "assists")),
    "app_records_team_seasons": (("points", "points"), ("valuation", "pir"),
                                 ("total_rebounds", "total_rebounds"),
                                 ("assistances", "assists")),
}


def _metric_select(name, metric, source):
    if name == "app_records_player_seasons":
        return (
            f"SELECT p.competition_code, '{metric}' AS metric, "
            "row_number() OVER (ORDER BY p.\"" + source + "\" DESC, "
            "p.season_code, p.person_key, p.entry_ordinal) AS rank_ordinal, "
            "p.season_code, p.person_key, p.player_name, p.club_code, "
            f"p.club_name, p.\"{source}\" AS value "
            "FROM silver.season_player_stats_traditional AS p "
            "WHERE p.competition_code = %s AND p.phase_code = 'all' "
            f"AND p.mode = 'accumulated' AND p.\"{source}\" IS NOT NULL"
        )
    if name == "app_records_single_games":
        return (
            f"SELECT p.competition_code, '{metric}' AS metric, "
            f'row_number() OVER (ORDER BY p."{source}" DESC, p.season_code, '
            "p.game_code, p.person_key, p.side) AS rank_ordinal, "
            "p.season_code, p.game_code, g.scheduled_at, p.person_key, "
            "p.person_name AS player_name, p.club_code, p.club_name, "
            f'p."{source}" AS value FROM silver.game_player_stats AS p '
            "JOIN silver.games AS g ON g.competition_code = p.competition_code "
            "AND g.season_code = p.season_code AND g.game_code = p.game_code "
            "WHERE p.competition_code = %s AND g.played IS TRUE "
            f'AND p."{source}" IS NOT NULL'
        )
    if name == "app_records_team_seasons":
        return (
            f"SELECT competition_code, '{metric}' AS metric, "
            "row_number() OVER (ORDER BY value DESC, season_code, club_code) "
            "AS rank_ordinal, season_code, club_code, club_name, value FROM ("
            "SELECT competition_code, season_code, club_code, "
            "max(club_name) AS club_name, sum(value) AS value FROM ("
            "SELECT g.competition_code, g.season_code, "
            "CASE WHEN t.side = 'local' THEN g.local_club_code "
            "ELSE g.road_club_code END AS club_code, "
            "CASE WHEN t.side = 'local' THEN g.local_club_name "
            "ELSE g.road_club_name END AS club_name, "
            f't."{source}" AS value FROM silver.game_team_stats AS t '
            "JOIN silver.games AS g ON g.competition_code = t.competition_code "
            "AND g.season_code = t.season_code AND g.game_code = t.game_code "
            "WHERE t.competition_code = %s AND t.stats_kind = 'total' "
            "AND g.played IS TRUE) AS box "
            "WHERE club_code IS NOT NULL GROUP BY competition_code, season_code, "
            "club_code) AS totals WHERE value IS NOT NULL"
        )
    raise ValueError(f"Unknown Gold records table: {name}")


def select_sql(name):
    """A bounded, deterministic query built only from registered metric names."""
    if name not in RECORDS_TABLES:
        raise ValueError(f"Unknown Gold records table: {name}")
    parts = [_metric_select(name, metric, source) for metric, source in METRICS[name]]
    fields = ", ".join(f'"{field}"' for field in columns(name))
    return (f"SELECT {fields} FROM ({' UNION ALL '.join(parts)}) AS ranked "
            "WHERE rank_ordinal <= 50 ORDER BY metric, rank_ordinal", len(parts))


def read_rows(cursor, name, competition_code):
    query, count = select_sql(name)
    cursor.execute(query, (competition_code,) * count)
    return _dict_rows(cursor)
