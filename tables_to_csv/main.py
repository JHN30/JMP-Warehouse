"""Export the column-first PostgreSQL ETL tables to season-scoped CSV files."""

import argparse
import sys
import time
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path

if __package__:
    from .utils import (
        COMPETITION_CODES, TABLES, Tee, available_seasons, connect, count_rows,
        elapsed, existing_tables, export_table, physical_name, select_seasons,
    )
else:
    from utils import (
        COMPETITION_CODES, TABLES, Tee, available_seasons, connect, count_rows,
        elapsed, existing_tables, export_table, physical_name, select_seasons,
    )
from common.db import DEFAULT_CONFIG, log_directory  # noqa: E402  (path set by utils)


HERE = Path(__file__).resolve().parent
DEFAULT_OUTPUT_ROOT = HERE.parent / "data"


def build_parser():
    parser = argparse.ArgumentParser(
        description="Export the loaded app_* and etl_flat_* PostgreSQL tables to CSV (no API requests)."
    )
    parser.add_argument("-cp", "--competition", choices=COMPETITION_CODES,
                        default="euroleague", help="Default: euroleague.")
    parser.add_argument("-sc", "--season-code", nargs="+", default=["latest"],
                        help="Year, full code, inclusive range, current, latest, or all. "
                             "Default: latest season in the selected database tables.")
    parser.add_argument("-tb", "--table", nargs="+", default=["all"],
                        help="Logical table names; default: all existing flat tables. "
                             "Use --list-tables to see names.")
    parser.add_argument("--list-tables", action="store_true",
                        help="List logical and physical table names; no database connection.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Count database rows without writing CSV files.")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT,
                        help="Parent of <competition>_csv/<season>; default: repository data/.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG,
                        help="PostgreSQL connection JSON from postgres_etl.")
    return parser


def run(args, names):
    started = time.monotonic()
    connection = connect(args.config)
    try:
        connection.set_client_encoding("UTF8")
        connection.set_session(readonly=True, isolation_level="REPEATABLE READ")
        existing, missing_tables = existing_tables(connection, names)
        if missing_tables and args.table != ["all"]:
            raise ValueError("Selected PostgreSQL table(s) do not exist: " + ", ".join(
                physical_name(name) for name in missing_tables
            ))
        if missing_tables:
            print("Not loaded; skipping tables: " + ", ".join(
                physical_name(name) for name in missing_tables
            ), flush=True)
        if not existing:
            raise ValueError("No selected flat ETL tables exist in this database/search path.")

        season_sources = list(existing)
        if "seasons" not in season_sources:
            season_table, _ = existing_tables(connection, ["seasons"])
            season_sources = season_table + season_sources
        available = available_seasons(connection, args.competition, season_sources)
        seasons, missing_seasons = select_seasons(
            args.season_code, args.competition, available
        )
        connection.rollback()  # Begin a new, consistent read-only snapshot per season.
        if missing_seasons:
            print("Not loaded; skipping seasons: " + ", ".join(missing_seasons), flush=True)
        print(f"Competition: {args.competition}", flush=True)
        print(f"Seasons: {', '.join(seasons)}", flush=True)
        print("Tables: " + ", ".join(physical_name(name) for name in existing), flush=True)
        print(f"Mode: {'dry run' if args.dry_run else 'CSV export'}", flush=True)

        total = 0
        for season_code in seasons:
            print(f"\nSeason {season_code} | elapsed {elapsed(started)}", flush=True)
            for name in existing:
                table_started = time.monotonic()
                physical = physical_name(name)
                action = "counting" if args.dry_run else "exporting"
                print(f"  {physical}: {action} ...", flush=True)
                count = count_rows(connection, args.competition, season_code, name)
                if not args.dry_run:
                    destination = (args.output_root / f"{args.competition}_csv" /
                                   season_code / f"{physical}.csv")
                    export_table(connection, args.competition, season_code,
                                 name, destination)
                total += count
                status = "found" if args.dry_run else "exported"
                print(f"  {physical}: {count:,} rows {status} in {elapsed(table_started)} "
                      f"| total elapsed {elapsed(started)}", flush=True)
            connection.rollback()

        print(f"\nFinished: {total:,} rows across {len(seasons)} season(s) "
              f"in {elapsed(started)}" + (" (dry run; no CSV files written)"
                                       if args.dry_run else ""), flush=True)
        if not args.dry_run:
            print(f"Output root: {(args.output_root / f'{args.competition}_csv').resolve()}",
                  flush=True)
        return 0
    finally:
        connection.close()


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.list_tables:
        for name in TABLES:
            print(f"{name:40} {physical_name(name)}")
        return 0
    unknown = set(args.table) - {"all", *TABLES}
    if unknown:
        parser.error("Unknown table(s): " + ", ".join(sorted(unknown)))
    if "all" in args.table and len(args.table) != 1:
        parser.error("'all' must be used alone with --table")
    names = list(TABLES) if args.table == ["all"] else list(dict.fromkeys(args.table))

    log_path = log_directory("tables_to_csv") / f"logfile_{datetime.now():%Y%m%d_%H%M%S_%f}"
    with log_path.open("w", encoding="utf-8") as log:
        with redirect_stdout(Tee(sys.stdout, log)):
            try:
                return run(args, names)
            except KeyboardInterrupt:
                print("\nInterrupted. Database unchanged; completed CSV files remain.", flush=True)
                return 130
            except Exception as error:
                print(f"CSV export failed: {error}", flush=True)
                return 1


if __name__ == "__main__":
    sys.exit(main())
