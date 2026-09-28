"""Derived postseason player rows from typed Silver game and box-score rows."""

from collections import defaultdict
from decimal import Decimal, ROUND_HALF_EVEN


PHASES = frozenset({"PI", "PO", "FF"})
COUNTING = (
    "points", "two_pointers_made", "two_pointers_attempted",
    "three_pointers_made", "three_pointers_attempted", "free_throws_made",
    "free_throws_attempted", "offensive_rebounds", "defensive_rebounds",
    "total_rebounds", "assists", "steals", "turnovers", "blocks",
    "blocks_against", "fouls_committed", "fouls_drawn", "pir",
)
PERCENTAGES = {
    "two_pointers_percentage": ("two_pointers_made", "two_pointers_attempted"),
    "three_pointers_percentage": ("three_pointers_made", "three_pointers_attempted"),
    "free_throws_percentage": ("free_throws_made", "free_throws_attempted"),
}
DOUBLE_MEASURES = ("points", "total_rebounds", "assists", "steals", "blocks")
TABLES = ("season_player_stats_traditional", "season_player_stats_misc")


def decimal(value):
    return Decimal(str(value))


def one_decimal(value):
    return decimal(value).quantize(Decimal("0.1"), rounding=ROUND_HALF_EVEN)


def _total(appearances, metric):
    values = [row.get(metric) for _, row in appearances]
    return None if any(value is None for value in values) else sum(map(decimal, values))


def _double_count(row):
    return sum((row.get(metric) or 0) >= 10 for metric in DOUBLE_MEASURES)


def derive_rows(games, box_scores, identities=None, clubs=None):
    """Return table -> sorted PS rows, ready for registered Gold columns.

    Games and box scores use Silver column names. Identity and club maps supply
    only optional v3 display fields, never a cross-season player identity.
    """
    identities = identities or {}
    clubs = clubs or {}
    postseason = sorted(
        (game for game in games if game["played"] is True and
         game["phase_code"] in PHASES),
        key=lambda game: (str(game.get("scheduled_at") or ""), game["game_code"]),
    )
    game_by_code = {game["game_code"]: game for game in postseason}
    club_games = defaultdict(int)
    for game in postseason:
        for column in ("local_club_code", "road_club_code"):
            if game.get(column):
                club_games[game[column]] += 1
    by_game = defaultdict(list)
    for row in box_scores:
        if row["game_code"] in game_by_code and row.get("person_key") and \
                not row["person_key"].startswith("unknown-") and \
                row.get("seconds_played") is not None and row["seconds_played"] > 0:
            by_game[row["game_code"]].append(row)
    by_player = defaultdict(list)
    for game in postseason:
        for row in by_game[game["game_code"]]:
            by_player[row["person_key"]].append((game, row))

    result = {table: [] for table in TABLES}
    for person_key, appearances in by_player.items():
        played = len(appearances)
        latest = appearances[-1][1]
        club_code = latest.get("club_code")
        identity = identities.get(person_key) or {}
        club = clubs.get(club_code) or {}
        base = {
            "phase_code": "PS", "person_key": person_key,
            "club_code": club_code, "player_name": latest.get("person_name"),
            "club_name": latest.get("club_name"),
            "player_age": identity.get("player_age"),
            "player_image_url": identity.get("player_image_url"),
            "club_tv_codes": club.get("club_tv_codes"),
            "club_image_url": club.get("club_image_url"),
            "player_ranking": None,
            "games_played": played,
            "games_started": sum(row.get("started") is True for _, row in appearances),
        }
        minutes = sum(decimal(row["seconds_played"]) for _, row in appearances) / 60
        totals = {metric: _total(appearances, metric) for metric in COUNTING}
        percentages = {}
        for metric, (made, attempted) in PERCENTAGES.items():
            numerator, denominator = totals[made], totals[attempted]
            percentages[metric] = (None if numerator is None or not denominator else
                                   one_decimal(numerator * 100 / denominator))
        misc = dict(base, minutes_played=minutes / played,
                    wins=sum(_won(game, row) is True for game, row in appearances),
                    losses=sum(_won(game, row) is False for game, row in appearances),
                    double_doubles=sum(_double_count(row) >= 2 for _, row in appearances),
                    triple_doubles=sum(_double_count(row) >= 3 for _, row in appearances))
        variants = {
            "season_player_stats_traditional": (
                dict(base, minutes_played=minutes, **totals, **percentages),
                dict(base, minutes_played=minutes / played,
                     **{metric: None if value is None else one_decimal(value / played)
                        for metric, value in totals.items()}, **percentages),
            ),
            "season_player_stats_misc": (misc, dict(misc)),
        }
        for table, (accumulated, per_game) in variants.items():
            accumulated["mode"] = "accumulated"
            result[table].append(accumulated)
            if played * 2 > club_games[club_code]:
                per_game["mode"] = "perGame"
                result[table].append(per_game)

    for table, rows in result.items():
        for mode in ("accumulated", "perGame"):
            selected = [row for row in rows if row["mode"] == mode]
            primary = "minutes_played" if table.endswith("traditional") else "games_played"
            selected.sort(key=lambda row: (-row[primary], -row["minutes_played"],
                                           row["person_key"]))
            for ordinal, row in enumerate(selected):
                row["entry_ordinal"] = ordinal
        rows.sort(key=lambda row: (row["mode"], row["entry_ordinal"]))
    return result


def _won(game, row):
    if row.get("side") not in {"local", "road"}:
        return None
    own = game.get(f'{row["side"]}_score')
    other = game.get("road_score" if row["side"] == "local" else "local_score")
    return own > other if own is not None and other is not None else None


def _dict_rows(cursor):
    names = [column[0] for column in cursor.description]
    return [dict(zip(names, values)) for values in cursor.fetchall()]


def read_rows(cursor, competition_code, season_code):
    """Build expected PS rows from Silver only, including optional v3 display fields."""
    scope = (competition_code, season_code)
    cursor.execute(
        'SELECT game_code, played, phase_code, scheduled_at, local_club_code, '
        'road_club_code, local_score, road_score FROM silver.games '
        'WHERE competition_code = %s AND season_code = %s '
        "AND played IS TRUE AND phase_code IN ('PI', 'PO', 'FF')", scope,
    )
    games = _dict_rows(cursor)
    if not games:
        return {table: [] for table in TABLES}
    fields = ("p.game_code", "p.side", "p.person_key", "p.person_name",
              "p.club_code", "p.club_name", "p.seconds_played", "p.started",
              *(f"p.{metric}" for metric in COUNTING))
    cursor.execute(
        f'SELECT {", ".join(fields)} FROM silver.game_player_stats AS p '
        'JOIN silver.games AS g ON g.competition_code = p.competition_code '
        'AND g.season_code = p.season_code AND g.game_code = p.game_code '
        'WHERE p.competition_code = %s AND p.season_code = %s '
        "AND g.played IS TRUE AND g.phase_code IN ('PI', 'PO', 'FF')", scope,
    )
    box_scores = _dict_rows(cursor)
    cursor.execute(
        'SELECT person_key, club_code, player_age, player_image_url, '
        'club_tv_codes, club_image_url '
        'FROM silver.season_player_stats_traditional '
        'WHERE competition_code = %s AND season_code = %s '
        "AND phase_code = 'all' AND mode = 'accumulated' "
        'ORDER BY entry_ordinal', scope,
    )
    identities, clubs = {}, {}
    for row in _dict_rows(cursor):
        identities.setdefault(row["person_key"], row)
        if row["club_code"]:
            clubs.setdefault(row["club_code"], row)
    return derive_rows(games, box_scores, identities, clubs)
