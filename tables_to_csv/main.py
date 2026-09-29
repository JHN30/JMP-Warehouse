"""Export every silver and gold table to one CSV file per table, for SQL Server (SSMS)."""

import argparse
import sys
import time
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path

if __package__:
    from .utils import (
        COMPETITION_CODES, LAYERS, Tee, available_seasons, connect, count_rows,
        discover_tables, elapsed, export_table, select_seasons,
    )
else:
    from utils import (
        COMPETITION_CODES, LAYERS, Tee, available_seasons, connect, count_rows,
        discover_tables, elapsed, export_table, select_seasons,
    )
from common.db import DEFAULT_CONFIG, log_directory  # noqa: E402  (path set by utils)


HERE = Path(__file__).resolve().parent
DEFAULT_OUTPUT_ROOT = HERE.parent / "data"


def build_parser():
    parser = argparse.ArgumentParser(
        description="Export every silver and gold table to one CSV file per table "
                    "(no API requests)."
    )
    parser.add_argument("-cp", "--competition", choices=COMPETITION_CODES,
                        default="euroleague", help="Default: euroleague.")
    parser.add_argument("-sc", "--season-code", nargs="+", default=["all"],
                        help="Year, full code, inclusive range, current, latest, or all. "
                             "Default: all. Applies to tables with a season_code column.")
    parser.add_argument("-tb", "--table", nargs="+", default=["all"],
                        help="Table names (the same name in both layers exports both); "
                             "default: every table. Use --list-tables to see them.")
    parser.add_argument("--layer", choices=("all", *LAYERS), default="all",
                        help="Schema to export. Default: all.")
    parser.add_argument("--list-tables", action="store_true",
                        help="List the tables found in the database; no files are written.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Count database rows without writing CSV files.")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT,
                        help="Parent of csv_export/; default: repository data/.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG,
                        help="PostgreSQL connection JSON from postgres_etl.")
    return parser


def select_tables(found, names):
    """The discovered tables named in `names` (or all); unknown names are an error."""
    if names == ["all"]:
        return found
    known = {table for _, table in found}
    unknown = sorted(set(names) - known)
    if unknown:
        raise ValueError("Table(s) not found in the selected layers: " + ", ".join(unknown))
    return {key: spec for key, spec in found.items() if key[1] in names}


def run(args):
    started = time.monotonic()
    layers = LAYERS if args.layer == "all" else (args.layer,)
    connection = connect(args.config)
    try:
        connection.set_client_encoding("UTF8")
        connection.set_session(readonly=True, isolation_level="REPEATABLE READ")
        found = discover_tables(connection, layers)
        if not found:
            raise ValueError("No tables found in the " + " or ".join(layers) + " schema.")
        if args.list_tables:
            for schema, table in found:
                print(f"{schema:8} {table}")
            return 0
        tables = select_tables(found, args.table)
        seasons = None
        if args.season_code != ["all"]:
            seasons, missing = select_seasons(args.season_code, args.competition,
                                              available_seasons(connection, args.competition))
            if missing:
                print("Not loaded; skipping seasons: " + ", ".join(missing), flush=True)
        print(f"Competition: {args.competition}", flush=True)
        print("Seasons: " + (", ".join(seasons) if seasons else "all"), flush=True)
        print(f"Tables: {len(tables)} in {', '.join(layers)}", flush=True)
        print(f"Mode: {'dry run' if args.dry_run else 'CSV export'}", flush=True)

        total = 0
        for (schema, table), spec in tables.items():
            table_started = time.monotonic()
            count = count_rows(connection, schema, table, spec, args.competition, seasons)
            if not args.dry_run:
                destination = (args.output_root / "csv_export" / args.competition /
                               schema / f"{table}.csv")
                export_table(connection, schema, table, spec, args.competition, seasons,
                             destination)
            total += count
            print(f"  {schema}.{table}: {count:,} rows "
                  f"{'found' if args.dry_run else 'exported'} in {elapsed(table_started)} "
                  f"| total elapsed {elapsed(started)}", flush=True)

        print(f"\nFinished: {len(tables)} table(s), {total:,} rows in {elapsed(started)}"
              + (" (dry run; no CSV files written)" if args.dry_run else ""), flush=True)
        if not args.dry_run:
            print(f"Output root: "
                  f"{(args.output_root / 'csv_export' / args.competition).resolve()}",
                  flush=True)
        return 0
    finally:
        connection.close()


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if "all" in args.table and len(args.table) != 1:
        parser.error("'all' must be used alone with --table")

    log_path = log_directory("tables_to_csv") / f"logfile_{datetime.now():%Y%m%d_%H%M%S_%f}"
    with log_path.open("w", encoding="utf-8") as log:
        with redirect_stdout(Tee(sys.stdout, log)):
            try:
                return run(args)
            except KeyboardInterrupt:
                print("\nInterrupted. Database unchanged; completed CSV files remain.", flush=True)
                return 130
            except Exception as error:
                print(f"CSV export failed: {error}", flush=True)
                return 1


if __name__ == "__main__":
    sys.exit(main())
