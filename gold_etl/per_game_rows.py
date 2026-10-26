"""perGame season rows the feed omits for players below its games threshold.

The feed lists every player who played in accumulated mode but only qualifiers in
perGame mode. The missing perGame row is a pure function of the same player's
accumulated row, so it is derived from that row and flagged is_calculated.
"""

from decimal import Decimal

from gold_etl.postseason import COUNTING, one_decimal
from gold_etl.qualification import scope_min_games, scope_rounds
from gold_etl.schema import physical_name
from gold_etl.schema import columns


MINUTES_PLACES = Decimal(1).scaleb(-12)
# Written by the row builder, not copied from the accumulated row.
OWN_COLUMNS = frozenset({"mode", "entry_ordinal", "player_ranking", "is_calculated",
                         "min_games", "qualified"})


def derive_per_game(name, accumulated):
    """One perGame row from an accumulated row: counting stats become per-game averages."""
    row = dict(accumulated, mode="perGame", player_ranking=None, is_calculated=True)
    if name == "season_player_stats_traditional":
        games = Decimal(row["games_played"])
        for metric in COUNTING:
            if row.get(metric) is not None:
                row[metric] = one_decimal(Decimal(row[metric]) / games)
        if row.get("minutes_played") is not None:
            row["minutes_played"] = (Decimal(row["minutes_played"]) / games
                                     ).quantize(MINUTES_PLACES)
    return row


def calculated_rows(name, missing, last_ordinals):
    """perGame rows for accumulated rows without one, appended after the feed's ordinals.

    min_games and qualified are filled in afterwards for every row of the scope.
    """
    next_ordinal = {phase: last + 1 for phase, last in last_ordinals.items()}
    rows = []
    for accumulated in missing:
        row = derive_per_game(name, accumulated)
        phase = row["phase_code"]
        row["entry_ordinal"] = next_ordinal.get(phase, 0)
        next_ordinal[phase] = row["entry_ordinal"] + 1
        rows.append(row)
    return rows


def _dict_rows(cursor):
    names = [column[0] for column in cursor.description]
    return [dict(zip(names, values)) for values in cursor.fetchall()]


def read_missing_rows(cursor, name, competition_code, season_code):
    """Accumulated feed rows (not PS) that have no perGame row for the same player."""
    names = ", ".join(f'a."{column}"' for column in columns(name))
    cursor.execute(
        f'SELECT {names} FROM gold."{physical_name(name)}" AS a '
        'WHERE a.competition_code = %s AND a.season_code = %s '
        "AND a.phase_code <> 'PS' AND a.mode = 'accumulated' "
        f'AND NOT EXISTS (SELECT 1 FROM gold."{physical_name(name)}" AS b '
        'WHERE b.competition_code = a.competition_code AND b.season_code = a.season_code '
        "AND b.phase_code = a.phase_code AND b.mode = 'perGame' "
        'AND b.person_key = a.person_key) '
        'ORDER BY a.phase_code, a.entry_ordinal', (competition_code, season_code))
    return _dict_rows(cursor)


def read_last_ordinals(cursor, name, competition_code, season_code):
    cursor.execute(
        f'SELECT phase_code, max(entry_ordinal) FROM gold."{physical_name(name)}" '
        "WHERE competition_code = %s AND season_code = %s AND mode = 'perGame' "
        "AND phase_code <> 'PS' GROUP BY phase_code", (competition_code, season_code))
    return {phase: last for phase, last in cursor.fetchall()}


def set_qualification(cursor, name, competition_code, season_code, phases=None):
    """Set min_games and qualified on every row of the given phases (default: all but PS)."""
    rounds = scope_rounds(cursor, competition_code, season_code)
    if phases is None:
        cursor.execute(
            f'SELECT DISTINCT phase_code FROM gold."{physical_name(name)}" '
            "WHERE competition_code = %s AND season_code = %s AND phase_code <> 'PS'",
            (competition_code, season_code))
        phases = [phase for (phase,) in cursor.fetchall()]
    for phase in phases:
        threshold = scope_min_games(rounds, phase, season_code)
        cursor.execute(
            f'UPDATE gold."{physical_name(name)}" SET "min_games" = %s, "qualified" = "games_played" >= %s '
            'WHERE competition_code = %s AND season_code = %s AND phase_code = %s',
            (threshold, threshold, competition_code, season_code, phase))


def finalize_player_stats(cursor, name, competition_code, season_code):
    """Add the missing perGame rows and set qualification; returns the rows added."""
    from psycopg2.extras import execute_values

    missing = read_missing_rows(cursor, name, competition_code, season_code)
    last = read_last_ordinals(cursor, name, competition_code, season_code)
    rows = calculated_rows(name, missing, last)
    if rows:
        fields = columns(name)
        names = ", ".join(f'"{field}"' for field in fields)
        execute_values(cursor, f'INSERT INTO gold."{physical_name(name)}" ({names}) VALUES %s',
                       [tuple(row[field] for field in fields) for row in rows],
                       page_size=1000)
    set_qualification(cursor, name, competition_code, season_code)
    return len(rows)
