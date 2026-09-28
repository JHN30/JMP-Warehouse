"""Eight historical coverage items for each season and fixture."""

from collections import defaultdict

from gold_etl.standings import _dict_rows


ITEMS = (
    ("boxScores", "Box scores"),
    ("periodScores", "Period scores"),
    ("officialStandings", "Official standings"),
    ("rosters", "Rosters"),
    ("playerPhotos", "Player photos"),
    ("seasonStatistics", "Season statistics"),
    ("shotLocations", "Shot locations"),
    ("playByPlay", "Play-by-play"),
)
LABELS = dict(ITEMS)
ROSTER_ITEMS = frozenset({"officialStandings", "rosters", "seasonStatistics"})


def item(key, available, applicable):
    if applicable == 0:
        status = "notYetApplicable"
    elif available == 0:
        status = "unavailable"
    elif available >= applicable:
        status = "available"
    else:
        status = "incomplete" if key in ROSTER_ITEMS else "partial"
    return {"key": key, "label": LABELS[key], "status": status,
            "availableCount": available, "applicableCount": applicable}


def derive_rows(games, clubs, box_games, period_games, standings_clubs,
                roster_clubs, photos, stats_players, shot_games, play_games):
    games = sorted(games, key=lambda game: game["game_code"])
    played = {game["game_code"] for game in games if game.get("played") is True}
    photo_by_game = defaultdict(set)
    for game_code, person_key in photos:
        if game_code in played:
            photo_by_game[game_code].add(person_key)
    season_items = [
        item("boxScores", len(box_games & played), len(played)),
        item("periodScores", len(period_games & played), len(played)),
        item("officialStandings", len(standings_clubs), len(clubs)),
        item("rosters", len(roster_clubs), len(clubs)),
        item("playerPhotos", len(set().union(*photo_by_game.values())), len(played)),
        item("seasonStatistics", len(stats_players), len(clubs)),
        item("shotLocations", len(shot_games & played), len(played)),
        item("playByPlay", len(play_games & played), len(played)),
    ]
    season_wide = {value["key"]: value for value in season_items}
    game_rows = []
    for game in games:
        code = game["game_code"]
        applicable = int(code in played)
        game_rows.append({"game_code": code, "items": [
            item("boxScores", int(bool(applicable and code in box_games)), applicable),
            item("periodScores", int(bool(applicable and code in period_games)), applicable),
            season_wide["officialStandings"], season_wide["rosters"],
            item("playerPhotos", len(photo_by_game[code]), applicable),
            season_wide["seasonStatistics"],
            item("shotLocations", int(bool(applicable and code in shot_games)), applicable),
            item("playByPlay", int(bool(applicable and code in play_games)), applicable),
        ]})
    return {"app_coverage_seasons": [{"items": season_items}],
            "app_coverage_games": game_rows}


def _values(cursor, query, scope, field):
    cursor.execute(query, scope)
    return {row[field] for row in _dict_rows(cursor)}


def read_rows(cursor, competition_code, season_code):
    scope = (competition_code, season_code)
    cursor.execute('SELECT game_code, played FROM silver.games '
                   'WHERE competition_code = %s AND season_code = %s', scope)
    games = _dict_rows(cursor)
    clubs = _values(cursor, 'SELECT club_code FROM silver.clubs '
                    'WHERE competition_code = %s AND season_code = %s', scope, "club_code")
    box = _values(cursor, 'SELECT DISTINCT game_code FROM silver.game_team_stats '
                  "WHERE competition_code = %s AND season_code = %s AND stats_kind = 'total'",
                  scope, "game_code")
    period = _values(cursor, 'SELECT DISTINCT game_code FROM silver.game_period_scores '
                     'WHERE competition_code = %s AND season_code = %s', scope, "game_code")
    standings = _values(cursor, 'SELECT DISTINCT club_code FROM silver.standings_basic '
                        'WHERE competition_code = %s AND season_code = %s', scope, "club_code")
    rosters = _values(cursor, 'SELECT DISTINCT club_code FROM silver.registrations '
                      'WHERE competition_code = %s AND season_code = %s '
                      'AND club_code IS NOT NULL', scope, "club_code")
    cursor.execute('SELECT DISTINCT game_code, person_key FROM silver.game_player_stats '
                   'WHERE competition_code = %s AND season_code = %s '
                   'AND headshot_url IS NOT NULL', scope)
    photos = {(row["game_code"], row["person_key"]) for row in _dict_rows(cursor)}
    stats = _values(cursor, 'SELECT DISTINCT person_key '
                    'FROM silver.season_player_stats_traditional '
                    'WHERE competition_code = %s AND season_code = %s', scope, "person_key")
    shots = _values(cursor, 'SELECT DISTINCT game_code FROM silver.shots '
                    'WHERE competition_code = %s AND season_code = %s', scope, "game_code")
    play = _values(cursor, 'SELECT DISTINCT game_code FROM silver.play_by_play '
                   'WHERE competition_code = %s AND season_code = %s', scope, "game_code")
    return derive_rows(games, clubs, box, period, standings, rosters,
                       photos, stats, shots, play)
