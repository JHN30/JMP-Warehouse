"""Regularized adjusted plus-minus per player and season (feature 29d).

Every stored lineup stint of feature 29b gives two observations, one per team: the team's points
per 100 possessions, weighted by its counted possessions, explained by an intercept, the five
offensive players' offense coefficients and the five defenders' defense coefficients (entered
with a minus sign, so a positive defense coefficient means fewer points allowed). A ridge penalty
on the coefficients, chosen per season by cross-validation over whole games (the strongest
penalty within 0.01% of the no-player error of the best one), shrinks small samples toward
zero. numpy is imported inside the solver so only this table depends on it. Nothing reads Gold or Neon.
"""

from collections import defaultdict
from decimal import Decimal

from gold_etl.team_pbp import read_silver

PENALTIES = (250, 500, 1000, 2000, 4000, 8000, 16000, 32000, 64000)
FOLDS = 5
# Stint outcomes are noisy, so the best penalty gains only a few tenths of a percent over a
# model without players; ties within this share of that no-player error prefer more shrinkage.
TOLERANCE = 1e-4
PLACES = Decimal("0.0001")
LINEUP_SIZE = 5


def _numpy():
    try:
        import numpy
    except ImportError as error:
        raise ValueError("gold.app_player_rapm needs numpy; install it in the Python environment "
                         "first") from error
    return numpy


def _normal(np, index, sign, weight, target, size):
    """X'WX and X'Wy for sparse rows with the given column indexes and signs."""
    flat = (index[:, :, None] * size + index[:, None, :]).ravel()
    pair = (weight[:, None, None] * sign[None, :, None] * sign[None, None, :]).ravel()
    matrix = np.bincount(flat, weights=pair, minlength=size * size).reshape(size, size)
    moment = ((weight * target)[:, None] * sign[None, :]).ravel()
    vector = np.bincount(index.ravel(), weights=moment, minlength=size)
    return matrix, vector


def _fit(np, index, sign, weight, value, size, penalty, game_folds=None, penalties=PENALTIES):
    """Coefficients for a season; `game_folds` gives each observation's fold for the
    cross-validated choice of the penalty from `penalties` (None: use `penalty`)."""
    def solve(rows, lam):
        mean = np.average(value[rows], weights=weight[rows])
        matrix, vector = _normal(np, index[rows], sign, weight[rows], value[rows] - mean, size)
        return mean, np.linalg.solve(matrix + lam * np.eye(size), vector)

    everything = np.arange(len(value))
    if game_folds is not None:
        errors, null = np.zeros(len(penalties)), 0.0
        for fold in range(int(game_folds.max()) + 1):
            train, test = everything[game_folds != fold], everything[game_folds == fold]
            if not len(test) or not len(train):
                continue
            mean = np.average(value[train], weights=weight[train])
            matrix, vector = _normal(np, index[train], sign, weight[train],
                                     value[train] - mean, size)
            values, vectors = np.linalg.eigh(matrix)
            projected = vectors.T @ vector
            null += (weight[test] * (value[test] - mean) ** 2).sum()
            for position, lam in enumerate(penalties):
                beta = vectors @ (projected / (values + lam))
                predicted = mean + (beta[index[test]] * sign).sum(axis=1)
                errors[position] += (weight[test] * (value[test] - predicted) ** 2).sum()
        penalty = max(lam for lam, error in zip(penalties, errors)
                      if error <= errors.min() + TOLERANCE * null)
    mean, beta = solve(everything, penalty)
    return penalty, mean, beta


def derive_rows(games, stints, players, penalties=PENALTIES):
    """Rows for `player_rapm`, sorted by scope and player."""
    played = {game["game_code"] for game in games if game.get("played") is True}
    names = {}
    for player in players:
        if player.get("person_name") and player["person_key"] not in names:
            names[player["person_key"]] = player["person_name"]
    seconds = defaultdict(int)
    rows_in = []
    for row in stints:
        if row["game_code"] not in played:
            continue
        members = row["players"].split(",")
        opponents = row["opponent_players"].split(",")
        if len(members) != LINEUP_SIZE or len(opponents) != LINEUP_SIZE:
            continue
        for person in members:
            seconds[person] += row["end_seconds"] - row["start_seconds"]
        if row["possessions_for"]:
            rows_in.append((row["game_code"], members, opponents, row["possessions_for"],
                            row["points_for"]))
    if not rows_in:
        return []
    np = _numpy()
    people = sorted({person for _, members, opponents, _, _ in rows_in
                     for person in members + opponents})
    position = {person: number for number, person in enumerate(people)}
    count = len(people)
    size = 2 * count
    index = np.array([[position[p] for p in members] + [count + position[p] for p in opponents]
                      for _, members, opponents, _, _ in rows_in], dtype=np.int64)
    sign = np.array([1.0] * LINEUP_SIZE + [-1.0] * LINEUP_SIZE)
    weight = np.array([row[3] for row in rows_in], dtype=float)
    value = np.array([100.0 * row[4] / row[3] for row in rows_in])
    order = {code: number for number, code in enumerate(sorted({row[0] for row in rows_in}))}
    folds = np.array([order[row[0]] % FOLDS for row in rows_in])
    penalty, _, beta = _fit(np, index, sign, weight, value, size, None, folds, penalties)
    offense_poss, defense_poss = defaultdict(int), defaultdict(int)
    for _, members, opponents, possessions, _ in rows_in:
        for person in members:
            offense_poss[person] += possessions
        for person in opponents:
            defense_poss[person] += possessions
    rows = []
    for person in people:
        offense = Decimal(str(round(float(beta[position[person]]), 4))) + 0
        defense = Decimal(str(round(float(beta[count + position[person]]), 4))) + 0
        rows.append({"scope": "all", "person_key": person, "player_name": names.get(person),
                     "seconds": seconds[person], "possessions_offense": offense_poss[person],
                     "possessions_defense": defense_poss[person],
                     "penalty": Decimal(penalty), "offense": offense.quantize(PLACES),
                     "defense": defense.quantize(PLACES),
                     "rapm": (offense + defense).quantize(PLACES)})
    return rows


def read_rows(cursor, competition_code, season_code):
    return derive_rows(*read_silver(cursor, competition_code, season_code,
                                    ("game_team_lineup_stints", "game_player_stats")))
