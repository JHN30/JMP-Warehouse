"""One Gold registration row per person, club and role in a season.

A club can deregister a person and register them again in the same season; Silver keeps
every source registration, the app reads Gold as roster membership.
"""

from gold_etl.postseason import _dict_rows
from gold_etl.schema import scope_predicate, source_columns


GROUP = ("competition_code", "season_code", "person_key", "club_code", "role_code")


def _recency(row):
    # A missing date sorts first, so a period without one is never the latest.
    return tuple((row[field] is not None, row[field])
                 for field in ("start_at", "end_at", "external_id"))


def collapse(rows):
    """Merge the periods of each group; the latest period supplies the other columns."""
    groups = {}
    for row in rows:
        groups.setdefault(tuple(row[field] for field in GROUP), []).append(row)
    result = []
    for periods in groups.values():
        if len(periods) == 1:
            result.append(periods[0])
            continue
        starts = [period["start_at"] for period in periods if period["start_at"] is not None]
        ends = [period["end_at"] for period in periods if period["end_at"] is not None]
        result.append({**max(periods, key=_recency),
                       "active": any(period["active"] for period in periods),
                       "start_at": min(starts, default=None),
                       "end_at": max(ends, default=None)})
    return result


def read_rows(cursor, competition_code, season_code):
    fields = ", ".join(f'"{column}"' for column in source_columns("registrations"))
    cursor.execute(
        f'SELECT {fields} FROM silver."registrations" '
        f'WHERE {scope_predicate("registrations")} ORDER BY "registration_key"',
        (competition_code, season_code),
    )
    return collapse(_dict_rows(cursor))
