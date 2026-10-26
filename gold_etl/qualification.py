"""Postseason phases and minimum games for leaderboard qualification, matching the stats feeds."""

from collections import defaultdict


# EuroLeague: play-in, playoffs and Final Four.
EUROLEAGUE_POSTSEASON = frozenset({"PI", "PO", "FF"})
# EuroCup knockout phases, per season. The formats are recorded in
# blueprint/history/features/18c-eurocup-postseason.md.
EUROCUP_POSTSEASON = frozenset({"8F", "4F", "2F", "Final"})
# U2007's Last 32 and Last 16 were two-leg knockouts, although the API marks them as
# groups; in later seasons they are group stages.
EUROCUP_EXTRA_POSTSEASON = {"U2007": frozenset({"L32", "L16"})}
EUROCUP_GROUP_PHASES = frozenset({"RS", "TS", "L32", "L16"})
# Two-leg ties decided on aggregate points, by season and phase. Every other tie is a
# single game or a best-of-three decided on game wins.
_TWO_LEG_8F_TO_2F = frozenset({"8F", "4F", "2F"})
TWO_LEG_PHASES = {
    "U2002": _TWO_LEG_8F_TO_2F | {"Final"},
    **{f"U{year}": _TWO_LEG_8F_TO_2F for year in range(2003, 2007)},
    "U2007": frozenset({"L32", "L16"}),
    **{f"U{year}": frozenset({"4F"}) for year in range(2009, 2012)},
    "U2012": frozenset({"4F", "2F"}),
    **{f"U{year}": _TWO_LEG_8F_TO_2F | {"Final"} for year in range(2013, 2016)},
}
# The feed lists every Final Four player in perGame mode, so nobody is filtered out.
UNFILTERED_PHASES = frozenset({"FF"})


def _eurocup(season_code):
    return bool(season_code) and season_code.startswith("U")


def postseason_phases(season_code):
    """The postseason phase codes of one season."""
    if _eurocup(season_code):
        return EUROCUP_POSTSEASON | EUROCUP_EXTRA_POSTSEASON.get(season_code, frozenset())
    return EUROLEAGUE_POSTSEASON


def is_postseason(phase_code, season_code):
    return phase_code in postseason_phases(season_code)


def is_two_leg(phase_code, season_code):
    return phase_code in TWO_LEG_PHASES.get(season_code, frozenset())


def min_games(rounds, phase_code, season_code=None):
    """More than half of the rounds played so far in the scope.

    EuroCup knockout phases follow their feed instead: at least half, rounded up.
    """
    if phase_code in UNFILTERED_PHASES:
        return 1
    if _eurocup(season_code) and is_postseason(phase_code, season_code):
        return max(1, (rounds + 1) // 2)
    return rounds // 2 + 1


def scope_rounds(cursor, competition_code, season_code):
    """Distinct played rounds per phase, plus the whole season ('all') and 'PS'."""
    cursor.execute(
        'SELECT DISTINCT phase_code, round_number FROM silver.games '
        'WHERE competition_code = %s AND season_code = %s AND played IS TRUE '
        'AND round_number IS NOT NULL', (competition_code, season_code))
    rounds = defaultdict(set)
    postseason = postseason_phases(season_code)
    for phase_code, round_number in cursor.fetchall():
        rounds[phase_code].add(round_number)
        rounds["all"].add(round_number)
        if phase_code in postseason:
            rounds["PS"].add(round_number)
    return {scope: len(numbers) for scope, numbers in rounds.items()}


def scope_min_games(rounds, phase_code, season_code=None):
    return min_games(rounds.get(phase_code, 0), phase_code, season_code)
