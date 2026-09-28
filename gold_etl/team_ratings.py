"""League-relative, SRS/SOS/SOV and opponent-adjusted team ratings after every round.

Rows match `team_round_stats` (same scopes, rounds and clubs). Everything is
cumulative through the round and built from the same counted games. SRS and the
adjusted ratings need a connected game graph; otherwise those columns are NULL.
"""

from collections import defaultdict
from decimal import Decimal

from gold_etl.team_rounds import _counted_games, _scopes, read_tables

PLACES = Decimal("0.000001")


def _solve(matrix, vector):
    """Gaussian elimination with partial pivoting; the systems are at most ~25 x 25."""
    n = len(vector)
    rows = [list(map(float, matrix[i])) + [float(vector[i])] for i in range(n)]
    for column in range(n):
        pivot = max(range(column, n), key=lambda r: abs(rows[r][column]))
        if abs(rows[pivot][column]) < 1e-12:
            raise ValueError("singular rating system")
        rows[column], rows[pivot] = rows[pivot], rows[column]
        for r in range(column + 1, n):
            factor = rows[r][column] / rows[column][column]
            if factor:
                for c in range(column, n + 1):
                    rows[r][c] -= factor * rows[column][c]
    result = [0.0] * n
    for r in range(n - 1, -1, -1):
        total = rows[r][n] - sum(rows[r][c] * result[c] for c in range(r + 1, n))
        result[r] = total / rows[r][r]
    return result


def _dec(value):
    return None if value is None else Decimal(repr(round(value, 9))).quantize(PLACES)


def _connected(clubs, games_between):
    seen, stack = {clubs[0]}, [clubs[0]]
    while stack:
        club = stack.pop()
        for other in clubs:
            if other not in seen and games_between.get((club, other)):
                seen.add(other)
                stack.append(other)
    return len(seen) == len(clubs)


class _State:
    """Cumulative graph of one scope: per-club sums and per-pair games and possessions."""

    def __init__(self):
        self.points_for = defaultdict(float)
        self.points_against = defaultdict(float)
        self.possessions = defaultdict(float)
        self.minutes = defaultdict(float)
        self.games = defaultdict(int)
        self.missing = False
        self.pair_games = defaultdict(int)
        self.pair_possessions = defaultdict(float)
        self.margin = defaultdict(float)
        self.wins = defaultdict(list)          # club -> opponents it beat
        self.opponents = defaultdict(list)     # club -> every opponent faced

    def add(self, entry):
        club, opponent = entry["club"], entry["opponent"]
        values = (entry["own"].get("points"), entry["opp"].get("points"),
                  entry["possessions"], entry["minutes"])
        if not opponent or any(value is None for value in values):
            self.missing = True
            return
        points, against, possessions, minutes = map(float, values)
        self.points_for[club] += points
        self.points_against[club] += against
        self.possessions[club] += possessions
        self.minutes[club] += minutes
        self.games[club] += 1
        self.pair_games[(club, opponent)] += 1
        self.pair_possessions[(club, opponent)] += possessions
        self.margin[club] += points - against
        self.opponents[club].append(opponent)
        if entry["won"] is True:
            self.wins[club].append(opponent)


def _ratings(state, clubs):
    """Rating columns for every club of one scope-round (NULLs when not computable)."""
    blank = {name: None for name in (
        "league_offensive_rating", "league_pace", "relative_offensive_rating",
        "relative_defensive_rating", "relative_pace", "srs", "sos", "sov",
        "adj_offensive_rating", "adj_defensive_rating", "adj_net_rating")}
    result = {club: dict(blank, connected=False) for club in clubs}
    if state.missing or any(state.games[club] == 0 for club in clubs):
        return result
    total_possessions = sum(state.possessions[club] for club in clubs)
    if total_possessions == 0:
        return result
    league = 100 * sum(state.points_for[club] for club in clubs) / total_possessions
    league_pace = 40 * total_possessions / sum(state.minutes[club] for club in clubs)
    for club in clubs:
        possessions = state.possessions[club]
        result[club].update(
            league_offensive_rating=_dec(league), league_pace=_dec(league_pace),
            relative_offensive_rating=_dec(100 * state.points_for[club] / possessions - league),
            relative_defensive_rating=_dec(100 * state.points_against[club] / possessions - league),
            relative_pace=_dec(40 * possessions / state.minutes[club] - league_pace))
    if len(clubs) < 2 or not _connected(clubs, state.pair_games):
        return result
    n = len(clubs)
    index = {club: i for i, club in enumerate(clubs)}
    games = lambda i, j: state.pair_games.get((clubs[i], clubs[j]), 0)
    # SRS: (L + 11'/N) r = m, so r_i = MOV_i + mean opponent r_j with sum(r) = 0.
    matrix = [[(state.games[clubs[i]] if i == j else -games(i, j)) + 1 / n
               for j in range(n)] for i in range(n)]
    srs = _solve(matrix, [state.margin[club] for club in clubs])
    # Adjusted ratings: possession-weighted; a = adjusted net, t = offense + defense.
    weights = [[state.pair_possessions.get((clubs[i], clubs[j]), 0.0) / state.possessions[clubs[i]]
                for j in range(n)] for i in range(n)]
    share = [state.possessions[club] / total_possessions for club in clubs]
    net = [100 * (state.points_for[c] - state.points_against[c]) / state.possessions[c]
           for c in clubs]
    total = [100 * (state.points_for[c] + state.points_against[c]) / state.possessions[c]
             for c in clubs]
    adjusted_net = _solve([[(1.0 if i == j else 0.0) - weights[i][j] + share[j]
                            for j in range(n)] for i in range(n)], net)
    try:
        adjusted_total = _solve([[(1.0 if i == j else 0.0) + weights[i][j]
                                  for j in range(n)] for i in range(n)],
                                [value + 2 * league for value in total])
    except ValueError:
        # A bipartite game graph (for example after one round) cannot separate a club's
        # offense from its defense; the adjusted net rating is still defined.
        adjusted_total = None
    for club in clubs:
        i = index[club]
        opponents = state.opponents[club]
        beaten = state.wins[club]
        result[club].update(
            connected=True, srs=_dec(srs[i]),
            sos=_dec(sum(srs[index[o]] for o in opponents) / len(opponents)),
            sov=_dec(sum(srs[index[o]] for o in beaten) / len(beaten)) if beaten else None,
            adj_offensive_rating=None if adjusted_total is None
            else _dec((adjusted_total[i] + adjusted_net[i]) / 2),
            adj_defensive_rating=None if adjusted_total is None
            else _dec((adjusted_total[i] - adjusted_net[i]) / 2),
            adj_net_rating=_dec(adjusted_net[i]))
    return result


def derive_rows(games, team_stats, advanced, clubs=()):
    """Rows for `team_round_ratings`, sorted by scope, round and club."""
    by_scope = defaultdict(lambda: defaultdict(list))
    for entry in _counted_games(games, team_stats, advanced):
        for scope in _scopes(entry["phase"]):
            by_scope[scope][entry["round"]].append(entry)
    rows = []
    for scope in sorted(by_scope):
        state, present = _State(), set()
        for number in sorted(by_scope[scope]):
            for entry in by_scope[scope][number]:
                present.add(entry["club"])
                state.add(entry)
            members = sorted(present)
            for club, values in sorted(_ratings(state, members).items()):
                rows.append({"scope": scope, "round_number": number, "club_code": club,
                             **values})
    rows.sort(key=lambda row: (row["scope"], row["round_number"], row["club_code"]))
    return rows


def read_rows(cursor, competition_code, season_code):
    return derive_rows(*read_tables(cursor, competition_code, season_code))
