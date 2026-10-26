"""Postseason pairings derived from Silver games."""

from collections import defaultdict
from datetime import timezone

from gold_etl.qualification import is_two_leg, postseason_phases
from gold_etl.standings import _dict_rows


def _scheduled_at(value):
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z")


def _aggregate_winner(pairing, club_a, club_b):
    """Two-leg tie: the higher combined points over both played legs, else no winner."""
    if len(pairing) != 2 or any(game.get("played") is not True or game.get("local_score") is None
                                or game.get("road_score") is None for game in pairing):
        return None
    points = {club_a: 0, club_b: 0}
    for game in pairing:
        points[game["local_club_code"]] += game["local_score"]
        points[game["road_club_code"]] += game["road_score"]
    return (club_a if points[club_a] > points[club_b] else
            club_b if points[club_b] > points[club_a] else None)


def derive_rows(games, season_code=None):
    phases = postseason_phases(season_code)
    groups = defaultdict(list)
    for game in games:
        local, road = game.get("local_club_code"), game.get("road_club_code")
        if game.get("phase_code") not in phases or not local or not road or local == road:
            continue
        if game.get("status") == "cancelled":  # never a result (U2019)
            continue
        club_a, club_b = sorted((local, road))
        groups[(game["phase_code"], club_a, club_b)].append(game)
    rows = []
    for (phase, club_a, club_b), pairing in sorted(groups.items()):
        pairing.sort(key=lambda game: (game.get("round_number") is None,
                                       game.get("round_number") or 0,
                                       game["game_code"]))
        names = {}
        wins = {club_a: 0, club_b: 0}
        details = []
        for game in pairing:
            if game.get("local_club_name"):
                names[game["local_club_code"]] = game["local_club_name"]
            if game.get("road_club_name"):
                names[game["road_club_code"]] = game["road_club_name"]
            played = game.get("played") is True
            winner = game.get("match_winner_club_code") if played else None
            if winner in wins:
                wins[winner] += 1
            details.append({
                "gameCode": game["game_code"],
                "roundNumber": game.get("round_number"),
                "scheduledAt": _scheduled_at(game.get("scheduled_at")),
                "localClubCode": game["local_club_code"],
                "roadClubCode": game["road_club_code"],
                "localScore": game.get("local_score") if played else None,
                "roadScore": game.get("road_score") if played else None,
                "winnerClubCode": winner,
            })
        if is_two_leg(phase, season_code):
            winner = _aggregate_winner(pairing, club_a, club_b)
        else:
            winner = (club_a if wins[club_a] > wins[club_b] else
                      club_b if wins[club_b] > wins[club_a] else None)
        rows.append({"phase_code": phase, "club_a_code": club_a,
                     "club_b_code": club_b, "club_a_name": names.get(club_a),
                     "club_b_name": names.get(club_b),
                     "games_played": len(pairing), "club_a_wins": wins[club_a],
                     "club_b_wins": wins[club_b], "winner_club_code": winner,
                     "games": details})
    return rows


def read_rows(cursor, competition_code, season_code):
    cursor.execute(
        'SELECT phase_code, game_code, round_number, scheduled_at, played, '
        'local_club_code, road_club_code, local_club_name, road_club_name, '
        'local_score, road_score, match_winner_club_code, status FROM silver.games '
        'WHERE competition_code = %s AND season_code = %s AND phase_code = ANY(%s)',
        (competition_code, season_code, sorted(postseason_phases(season_code))))
    return derive_rows(_dict_rows(cursor), season_code)
