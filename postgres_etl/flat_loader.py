"""Transactional writer and validator for the column-first analytical tables."""

import time

from flat_schema import TABLES, add_column_sql, create_index_sql, create_table_sql, physical_name
from flat_transform import FlatSeason
from shared import connect, elapsed


class FlatDatabaseLoader:
    def __init__(self, data_root, competition, season_codes, tables, config_path, dry_run=False):
        self.data_root = data_root
        self.competition = competition
        self.season_codes = season_codes
        self.tables = tables
        self.config_path = config_path
        self.dry_run = dry_run

    def run(self):
        started = time.monotonic()
        total = 0
        connection = None
        try:
            if not self.dry_run:
                connection = connect(self.config_path)
            for season_code in self.season_codes:
                season = FlatSeason(self.data_root, self.competition, season_code)
                print(f"\nSeason {season_code} | elapsed {elapsed(started)}", flush=True)
                for name in self.tables:
                    files = season.files(name)
                    physical = physical_name(name)
                    if not files:
                        print(f"  {physical}: SKIP (no source files)", flush=True)
                        continue
                    table_start = time.monotonic()
                    print(f"  {physical}: processing {len(files)} source file(s) ...", flush=True)
                    if self.dry_run:
                        count = self._dry_run_table(season, name, files, table_start)
                    else:
                        count = self._load_table(connection, season, name, files, table_start)
                    total += count
                    status = "validated" if self.dry_run else "loaded"
                    print(f"  {physical}: {count:,} rows {status} in {elapsed(table_start)} "
                          f"| total elapsed {elapsed(started)}", flush=True)
        finally:
            if connection is not None:
                connection.close()
        print(f"\nFinished: {total:,} rows across {len(self.season_codes)} season(s) "
              f"in {elapsed(started)}" + (" (dry run; database unchanged)" if self.dry_run else ""),
              flush=True)
        return total

    @staticmethod
    def _dry_run_table(season, name, files, started):
        spec = TABLES[name]
        seen = set()
        count = 0
        for row in season.rows(name, files):
            identifier = tuple(row[column] for column in spec.key)
            if any(value is None for value in identifier):
                raise ValueError(f"Null key in {physical_name(name)}: {identifier}")
            if identifier in seen:
                raise ValueError(f"Duplicate key in {physical_name(name)}: {identifier}")
            seen.add(identifier)
            for field in spec.fields:
                if row[field.name] is None and "NOT NULL" in field.kind:
                    raise ValueError(f"Null {physical_name(name)}.{field.name}: {identifier}")
            count += 1
            if count % 10000 == 0:
                print(f"    {count:,} rows checked | {elapsed(started)}", flush=True)
        return count

    @staticmethod
    def _load_table(connection, season, name, files, started):
        from psycopg2.extras import Json, execute_values

        spec = TABLES[name]
        physical = physical_name(name)
        columns = [field.name for field in spec.fields]
        json_columns = {field.name for field in spec.fields if field.kind.startswith("JSONB")}
        column_sql = ", ".join(f'"{column}"' for column in columns)
        insert_sql = f'INSERT INTO "{physical}" ({column_sql}) VALUES %s'
        batch_size = 25 if name == "source_payloads" else 1000
        batch = []
        count = 0
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(create_table_sql(name))
                for statement in add_column_sql(name):
                    cursor.execute(statement)
                for statement in create_index_sql(name):
                    cursor.execute(statement)
                cursor.execute(
                    f'DELETE FROM "{physical}" WHERE "competition_code" = %s '
                    'AND "season_code" = %s',
                    (season.scope["competition_code"], season.season_code),
                )
                for row in season.rows(name, files):
                    batch.append(tuple(Json(row[column]) if column in json_columns else row[column]
                                       for column in columns))
                    count += 1
                    if len(batch) == batch_size:
                        execute_values(cursor, insert_sql, batch, page_size=batch_size)
                        batch.clear()
                    if count % 10000 == 0:
                        print(f"    {count:,} rows inserted | {elapsed(started)}", flush=True)
                if batch:
                    execute_values(cursor, insert_sql, batch, page_size=batch_size)
        return count
