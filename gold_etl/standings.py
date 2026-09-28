"""Page-shaped standings rows from the seven typed Silver feed tables."""

from collections import defaultdict
from datetime import datetime, timezone

from gold_etl.schema import (STANDINGS_CHILDREN, STANDINGS_FEEDS,
                             STANDINGS_RENAMES, columns, feed_fields)


KEY = ("competition_code", "season_code", "phase_code", "round_number", "club_code")


def iso_milliseconds(value):
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z")


def _key(row):
    return tuple(row[field] for field in KEY)


def _unique(rows, label):
    result = {}
    for row in rows:
        key = _key(row)
        if key in result:
            raise ValueError(f"Duplicate {label} key: {key}")
        result[key] = row
    return result


def derive_rows(feeds, clubs):
    """Return complete page rows; absent parent feeds retain all-NULL columns."""
    parents = {name: _unique(feeds.get(name, ()), name)
               for name, _ in STANDINGS_FEEDS}
    form = defaultdict(list)
    streaks = defaultdict(list)
    for name, target, ordinal in (
        (STANDINGS_CHILDREN[0], form, "result_ordinal"),
        (STANDINGS_CHILDREN[1], streaks, "streak_ordinal"),
    ):
        seen = set()
        for row in feeds.get(name, ()):
            key = _key(row)
            child_key = key + (row[ordinal],)
            if child_key in seen:
                raise ValueError(f"Duplicate {name} key: {child_key}")
            seen.add(child_key)
            target[key].append(row)
    crests = {(row["competition_code"], row["season_code"], row["club_code"]):
              row.get("crest_url") for row in clubs}
    result = []
    for key, basic in sorted(parents["standings_basic"].items()):
        row = {column: None for column in columns("app_standings")}
        row.update(dict(zip(KEY, key)))
        row.update(club_name=basic.get("club_name"),
                   club_tv_code=basic.get("club_tv_code"),
                   group_name=basic.get("group_name"),
                   crest_url=crests.get((key[0], key[1], key[4])))
        for name, prefix in STANDINGS_FEEDS:
            source = parents[name].get(key)
            if source is not None:
                for field in feed_fields(name):
                    target = f'{prefix}_{STANDINGS_RENAMES.get(field.name, field.name)}'
                    row[target] = source.get(field.name)
        row["form"] = [
            {"resultOrdinal": child["result_ordinal"], "result": child.get("result")}
            for child in sorted(form[key], key=lambda child: child["result_ordinal"])
        ]
        row["streak_history"] = [
            {"streakOrdinal": child["streak_ordinal"],
             "startAt": iso_milliseconds(child.get("start_at")),
             "endAt": iso_milliseconds(child.get("end_at")),
             "winLossRecord": child.get("win_loss_record")}
            for child in sorted(streaks[key], key=lambda child: child["streak_ordinal"])
        ]
        result.append(row)
    return result


def _dict_rows(cursor):
    names = [column[0] for column in cursor.description]
    return [dict(zip(names, values)) for values in cursor.fetchall()]


def read_rows(cursor, competition_code, season_code):
    """Read exactly the Silver tables used by the historical page contract."""
    scope = (competition_code, season_code)
    feeds = {}
    for name in [*(name for name, _ in STANDINGS_FEEDS), *STANDINGS_CHILDREN]:
        cursor.execute(f'SELECT * FROM silver."{name}" '
                       'WHERE competition_code = %s AND season_code = %s', scope)
        feeds[name] = _dict_rows(cursor)
    cursor.execute('SELECT competition_code, season_code, club_code, crest_url '
                   'FROM silver.clubs WHERE competition_code = %s AND season_code = %s', scope)
    return derive_rows(feeds, _dict_rows(cursor))
