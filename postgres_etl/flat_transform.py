"""Flatten cached responses into typed rows without per-row JSONB payloads."""

from decimal import Decimal, InvalidOperation

from flat_schema import TABLES
from raw_transform import RawSeason, parse_source_timestamp, utc_wall_time


def get_path(value, path):
    for component in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(component)
    return value


def cast(value, kind):
    if value is None or value == "":
        return None
    sql_type = kind.split()[0]
    if sql_type == "JSONB":
        return value
    if sql_type == "TEXT":
        if isinstance(value, (dict, list)):
            raise ValueError(f"Expected a scalar string, got {type(value).__name__}")
        return str(value).strip()
    if sql_type == "BOOLEAN":
        if isinstance(value, bool):
            return value
        if value in (0, 1, "0", "1"):
            return value in (1, "1")
        if isinstance(value, str) and value.lower() in ("true", "false"):
            return value.lower() == "true"
        raise ValueError(f"Invalid boolean: {value!r}")
    if sql_type == "INTEGER":
        try:
            number = Decimal(str(value))
            if not number.is_finite() or number != int(number):
                raise ValueError(f"Invalid integer: {value!r}")
            return int(number)
        except (InvalidOperation, TypeError) as error:
            raise ValueError(f"Invalid integer: {value!r}") from error
    if sql_type == "NUMERIC":
        if isinstance(value, str):
            value = value.strip().removesuffix("%").strip()
            # "NaN%" appears for 0/0 percentages: undefined, so NULL rather than a number.
            if value in ("", "-", "N/A", "n/a") or value.lower() == "nan":
                return None
        elif isinstance(value, float) and value != value:
            return None
        try:
            number = Decimal(str(value))
            if not number.is_finite():
                raise ValueError(f"Invalid number: {value!r}")
            return number
        except (InvalidOperation, TypeError) as error:
            raise ValueError(f"Invalid number: {value!r}") from error
    if sql_type == "TIMESTAMP":
        return utc_wall_time(parse_source_timestamp(value))
    if sql_type == "TIMESTAMPTZ":
        return parse_source_timestamp(value)
    raise ValueError(f"Unknown SQL type: {kind}")


class FlatSeason:
    def __init__(self, data_root, competition, season_code):
        self.raw = RawSeason(data_root, competition, season_code)
        self.scope = self.raw.scope
        self.season_code = season_code

    def files(self, name):
        return self.raw.files(TABLES[name].source)

    def rows(self, name, files=None):
        spec = TABLES[name]
        files = self.files(name) if files is None else files
        for source_row in self.raw.rows(spec.source, files):
            for candidate in self._expand(name, source_row):
                row = {}
                for field in spec.fields:
                    value = (candidate.get(field.path[1:]) if field.path.startswith("@")
                             else get_path(candidate.get("payload"), field.path))
                    try:
                        row[field.name] = cast(value, field.kind)
                    except (TypeError, ValueError) as error:
                        raise ValueError(
                            f"{name}.{field.name} from {field.path} "
                            f"({self.season_code}): {error}"
                        ) from error
                yield row

    @staticmethod
    def _expand(name, row):
        if name.startswith("season_stats_"):
            if row["category"] == name.removeprefix("season_stats_"):
                yield row
            return
        if name.startswith("season_team_stats_"):
            if row["feed"] == name.removeprefix("season_team_stats_"):
                yield row
            return
        if name.startswith("standings_") and name not in (
            "standings_calendar_streaks", "standings_basic_form"
        ):
            if row["feed"] == name.removeprefix("standings_"):
                yield row
            return
        if name == "standings_calendar_streaks":
            if row["feed"] != "calendarstandings":
                return
            for ordinal, streak in enumerate(row["payload"].get("streaks") or []):
                yield dict(row, streak_ordinal=ordinal, payload=streak)
            return
        if name == "standings_basic_form":
            if row["feed"] != "basicstandings":
                return
            for ordinal, result in enumerate(row["payload"].get("last5Form") or []):
                yield dict(row, result_ordinal=ordinal, result=result)
            return
        if name == "game_team_stats":
            coach = row["payload"].get("coach") or {}
            for kind in ("team", "total"):
                stats = row["payload"].get(kind)
                if isinstance(stats, dict):
                    yield dict(row, stats_kind=kind, coach_name=coach.get("name"),
                               payload=stats)
            return
        yield row
