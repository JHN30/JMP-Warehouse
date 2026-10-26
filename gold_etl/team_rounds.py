"""Cumulative team stats after every round, per scope, from Silver box scores.

Scopes are `all`, each phase, and `PS` (postseason phases). A club has a row for
every scope round from its first counted game on; rounds it skips carry its
previous cumulative values forward. Formulas restate feature 25's box-score
conventions, applied to cumulative totals rather than averages of game rates.
"""

from collections import defaultdict
from decimal import Decimal

from gold_etl.qualification import is_postseason
from gold_etl.schema import ROUND_MEASURES
from gold_etl.standings import _dict_rows

FT_WEIGHT = Decimal("0.44")
PLACES = Decimal("0.000001")
PYTHAGOREAN_EXPONENT = Decimal("10.25")
SUMMED = ("points",) + ROUND_MEASURES


def _num(value):
    return None if value is None else Decimal(str(value))


def _add(total, value):
    """Running sum; one missing input makes the cumulative value unavailable."""
    return None if total is None or value is None else total + _num(value)


def _div(numerator, denominator):
    if numerator is None or denominator is None or denominator == 0:
        return None
    return (numerator / denominator).quantize(PLACES)


def _counted_games(games, team_stats, advanced):
    """One entry per club per played game with a full box score."""
    totals = {(row["game_code"], row["side"]): row for row in team_stats
              if row["stats_kind"] == "total"}
    extra = {(row["game_code"], row["side"]): row for row in advanced}
    entries = []
    for game in games:
        code = game["game_code"]
        if (game.get("played") is not True or not game.get("phase_code")
                or game.get("round_number") is None):
            continue
        if any((code, side) not in totals or (code, side) not in extra
               for side in ("local", "road")):
            continue
        for side, other in (("local", "road"), ("road", "local")):
            club = game.get(f"{side}_club_code")
            if not club:
                continue
            winner = game.get("match_winner_club_code")
            entries.append({
                "phase": game["phase_code"], "round": game["round_number"],
                "season": game.get("season_code"),
                "club": club, "opponent": game.get(f"{other}_club_code"),
                "home": side == "local", "game_code": code,
                "name": game.get(f"{side}_club_name"),
                "own": totals[(code, side)], "opp": totals[(code, other)],
                "won": None if winner is None else winner == club,
                "possessions": extra[(code, side)].get("possessions"),
                "minutes": extra[(code, side)].get("game_minutes"),
            })
    return entries


def _scopes(phase, season_code=None):
    yield "all"
    yield phase
    if is_postseason(phase, season_code):
        yield "PS"


def _fresh():
    state = {"games_played": 0, "wins": 0, "losses": 0,
             "possessions": Decimal(0), "game_minutes": Decimal(0)}
    for name in SUMMED:
        state[f"own_{name}"] = state[f"opp_{name}"] = Decimal(0)
    return state


def _accumulate(state, entry):
    state["games_played"] += 1
    if entry["won"] is True:
        state["wins"] += 1
    elif entry["won"] is False:
        state["losses"] += 1
    state["possessions"] = _add(state["possessions"], entry["possessions"])
    state["game_minutes"] = _add(state["game_minutes"], entry["minutes"])
    for name in SUMMED:
        for side in ("own", "opp"):
            state[f"{side}_{name}"] = _add(state[f"{side}_{name}"], entry[side].get(name))


def _rates(state):
    own = {name: state[f"own_{name}"] for name in SUMMED}
    opp = {name: state[f"opp_{name}"] for name in SUMMED}
    games = state["games_played"]
    points_for, points_against = own["points"], opp["points"]
    possessions, minutes = state["possessions"], state["game_minutes"]

    def ratio(numerator, denominator):
        return _div(numerator, denominator)

    def efg(side):
        if side["field_goals_made"] is None or side["three_pointers_made"] is None:
            return None
        return ratio(side["field_goals_made"] + Decimal("0.5") * side["three_pointers_made"],
                     side["field_goals_attempted"])

    def tov(side):
        if any(side[name] is None for name in ("field_goals_attempted",
                                                "free_throws_attempted", "turnovers")):
            return None
        return ratio(side["turnovers"], side["field_goals_attempted"]
                     + FT_WEIGHT * side["free_throws_attempted"] + side["turnovers"])

    def rebound(mine, theirs):
        if mine is None or theirs is None:
            return None
        return ratio(mine, mine + theirs)

    rating = lambda points: ratio(None if points is None else 100 * points, possessions)
    offensive, defensive = rating(points_for), rating(points_against)
    both = points_for is not None and points_against is not None
    if both and (points_for > 0 or points_against > 0):
        share = (points_for ** PYTHAGOREAN_EXPONENT
                 / (points_for ** PYTHAGOREAN_EXPONENT + points_against ** PYTHAGOREAN_EXPONENT))
        pythagorean = share.quantize(PLACES)
    else:
        pythagorean = None
    true_shooting = None
    if own["points"] is not None and own["field_goals_attempted"] is not None \
            and own["free_throws_attempted"] is not None:
        true_shooting = ratio(own["points"], 2 * (own["field_goals_attempted"]
                                                  + FT_WEIGHT * own["free_throws_attempted"]))
    return {
        "points_for": points_for, "points_against": points_against,
        "mov": ratio(points_for - points_against, games) if both else None,
        "pythagorean_exponent": PYTHAGOREAN_EXPONENT,
        "pythagorean_win_pct": pythagorean,
        "pythagorean_wins": None if pythagorean is None else (pythagorean * games).quantize(PLACES),
        "pace": ratio(None if possessions is None else 40 * possessions, minutes),
        "offensive_rating": offensive, "defensive_rating": defensive,
        "net_rating": None if offensive is None or defensive is None else offensive - defensive,
        "efg_pct": efg(own), "tov_pct": tov(own),
        "orb_pct": rebound(own["offensive_rebounds"], opp["defensive_rebounds"]),
        "drb_pct": rebound(own["defensive_rebounds"], opp["offensive_rebounds"]),
        "ft_rate": ratio(own["free_throws_made"], own["field_goals_attempted"]),
        "opp_efg_pct": efg(opp), "opp_tov_pct": tov(opp),
        "opp_ft_rate": ratio(opp["free_throws_made"], opp["field_goals_attempted"]),
        "true_shooting_pct": true_shooting,
        "assist_ratio": ratio(own["assists"], own["field_goals_made"]),
    }


def derive_rows(games, team_stats, advanced, clubs):
    """Rows for `team_round_stats`, sorted by scope, round and club."""
    names = {club["club_code"]: club.get("name") for club in clubs}
    entries = _counted_games(games, team_stats, advanced)
    by_scope = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    fallback = {}
    for entry in entries:
        fallback.setdefault(entry["club"], entry["name"])
        for scope in _scopes(entry["phase"], entry["season"]):
            by_scope[scope][entry["club"]][entry["round"]].append(entry)
    rows = []
    for scope in sorted(by_scope):
        clubs_in_scope = by_scope[scope]
        rounds = sorted({r for played in clubs_in_scope.values() for r in played})
        for club, played in sorted(clubs_in_scope.items()):
            state = _fresh()
            for number in (r for r in rounds if r >= min(played)):
                for entry in played.get(number, ()):
                    _accumulate(state, entry)
                row = {"scope": scope, "round_number": number, "club_code": club,
                       "club_name": names.get(club) or fallback.get(club),
                       "games_played": state["games_played"], "wins": state["wins"],
                       "losses": state["losses"],
                       "possessions": state["possessions"],
                       "game_minutes": state["game_minutes"]}
                for name in ROUND_MEASURES:
                    for side in ("own", "opp"):
                        row[f"{side}_{name}"] = state[f"{side}_{name}"]
                row.update(_rates(state))
                rows.append(row)
    rows.sort(key=lambda row: (row["scope"], row["round_number"], row["club_code"]))
    return rows


def read_tables(cursor, competition_code, season_code):
    """Silver inputs shared by the round tables: games, totals, advanced rows, clubs."""
    scope = (competition_code, season_code)
    tables = []
    for query in (
        "SELECT * FROM silver.games WHERE competition_code = %s AND season_code = %s",
        "SELECT * FROM silver.game_team_stats WHERE competition_code = %s "
        "AND season_code = %s AND stats_kind = 'total'",
        "SELECT * FROM silver.game_team_advanced WHERE competition_code = %s "
        "AND season_code = %s",
        "SELECT club_code, name FROM silver.clubs WHERE competition_code = %s "
        "AND season_code = %s",
    ):
        cursor.execute(query, scope)
        tables.append(_dict_rows(cursor))
    return tables


def read_rows(cursor, competition_code, season_code):
    return derive_rows(*read_tables(cursor, competition_code, season_code))
