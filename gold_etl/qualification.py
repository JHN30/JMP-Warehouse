"""Minimum games for leaderboard qualification, matching the EuroLeague stats feed."""

from collections import defaultdict


POSTSEASON_PHASES = frozenset({"PI", "PO", "FF"})
# The feed lists every Final Four player in perGame mode, so nobody is filtered out.
UNFILTERED_PHASES = frozenset({"FF"})


def min_games(rounds, phase_code):
    """More than half of the rounds played so far in the scope."""
    return 1 if phase_code in UNFILTERED_PHASES else rounds // 2 + 1


def scope_rounds(cursor, competition_code, season_code):
    """Distinct played rounds per phase, plus the whole season ('all') and 'PS'."""
    cursor.execute(
        'SELECT DISTINCT phase_code, round_number FROM silver.games '
        'WHERE competition_code = %s AND season_code = %s AND played IS TRUE '
        'AND round_number IS NOT NULL', (competition_code, season_code))
    rounds = defaultdict(set)
    for phase_code, round_number in cursor.fetchall():
        rounds[phase_code].add(round_number)
        rounds["all"].add(round_number)
        if phase_code in POSTSEASON_PHASES:
            rounds["PS"].add(round_number)
    return {scope: len(numbers) for scope, numbers in rounds.items()}


def scope_min_games(rounds, phase_code):
    return min_games(rounds.get(phase_code, 0), phase_code)
