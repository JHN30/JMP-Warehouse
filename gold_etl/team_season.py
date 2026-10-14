"""Team-season own and opponent box-score totals from Silver."""

from collections import defaultdict
from decimal import Decimal

from gold_etl.schema import TEAM_MEASURE_COLUMNS
from gold_etl.standings import _dict_rows


def _number(value):
    return Decimal(str(value))


def derive_rows(games, team_stats, clubs, no_box_score=()):
    """Sum played games per phase and club; games without a box score (a
    forfeit's `*` stat gap) are not counted."""
    names = {club["club_code"]: club.get("name") for club in clubs}
    totals = {(row["game_code"], row["side"]): row for row in team_stats
              if row["stats_kind"] == "total"}
    skipped = set(no_box_score)
    groups = defaultdict(list)
    fallback = {}
    for game in sorted(games, key=lambda row: (str(row.get("scheduled_at") or ""),
                                               row["game_code"])):
        if (game.get("played") is not True or not game.get("phase_code")
                or game["game_code"] in skipped):
            continue
        for side, other in (("local", "road"), ("road", "local")):
            club_code = game.get(f"{side}_club_code")
            own = totals.get((game["game_code"], side))
            if not club_code or own is None:
                continue
            key = (game["phase_code"], club_code)
            groups[key].append((own, totals.get((game["game_code"], other))))
            fallback[key] = game.get(f"{side}_club_name")
    rows = []
    for (phase, club_code), appearances in sorted(groups.items()):
        row = {"phase_code": phase, "club_code": club_code,
               "club_name": names.get(club_code) or fallback.get((phase, club_code)),
               "games_played": len(appearances)}
        for target, source in TEAM_MEASURE_COLUMNS:
            for side, offset in (("own", 0), ("opp", 1)):
                values = [pair[offset].get(source) if pair[offset] is not None else None
                          for pair in appearances]
                row[f"{side}_{target}"] = (None if any(value is None for value in values)
                                            else sum(map(_number, values)))
        rows.append(row)
    return rows


def read_rows(cursor, competition_code, season_code):
    scope = (competition_code, season_code)
    cursor.execute('SELECT * FROM silver.games '
                   'WHERE competition_code = %s AND season_code = %s', scope)
    games = _dict_rows(cursor)
    cursor.execute('SELECT * FROM silver.game_team_stats '
                   'WHERE competition_code = %s AND season_code = %s', scope)
    team_stats = _dict_rows(cursor)
    cursor.execute('SELECT club_code, name FROM silver.clubs '
                   'WHERE competition_code = %s AND season_code = %s', scope)
    clubs = _dict_rows(cursor)
    cursor.execute("SELECT game_code FROM silver.game_stat_gaps "
                   "WHERE competition_code = %s AND season_code = %s AND stat_name = '*'",
                   scope)
    return derive_rows(games, team_stats, clubs, [row[0] for row in cursor.fetchall()])
