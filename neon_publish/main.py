"""Publish loaded seasons from local PostgreSQL to Neon (replaces the CSV/psql import)."""

import argparse
import sys
import time
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path

if __package__:
    from .publish import (APP_TABLES, NEON_URL_ENV, PLAYER_TABLES, RECORDS_TABLES, drop_old_names,
                          neon_connect, publish_records, publish_season)
else:
    from publish import (APP_TABLES, NEON_URL_ENV, PLAYER_TABLES, RECORDS_TABLES, drop_old_names,
                         neon_connect, publish_records, publish_season)

from common.db import DEFAULT_CONFIG, Tee, connect, elapsed, log_directory  # noqa: E402
from common.seasons import COMPETITION_CODES, select_seasons  # noqa: E402
from postgres_etl.flat_schema import physical_name, rename_local_tables  # noqa: E402  (path set by publish)
from tables_to_csv.utils import available_seasons  # noqa: E402


def build_parser():
    parser = argparse.ArgumentParser(
        description="Replace selected seasons of the web-app tables in Neon with the "
                    "rows in local PostgreSQL. No API requests are made."
    )
    parser.add_argument("-cp", "--competition", choices=COMPETITION_CODES,
                        default="euroleague", help="Default: euroleague.")
    parser.add_argument("-sc", "--season-code", nargs="+", default=["current"],
                        help="Year, full code, inclusive range, current, latest, or all "
                             "(seasons present in local PostgreSQL). Default: current.")
    parser.add_argument("-tb", "--table", nargs="+", default=["all"],
                        help="Logical table names; default: all web-app tables. "
                             "Use --list-tables to see them.")
    parser.add_argument("--list-tables", action="store_true",
                        help="List the published tables and exit.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Compare local and Neon row counts without changing Neon.")
    parser.add_argument("--drop-old-names", action="store_true",
                        help="Drop the old etl_flat_* views left in Neon by the rename to app_* "
                             "names. Only after the web app reads the app_* names; try "
                             "--dry-run first.")
    parser.add_argument("--allow-shrink", action="store_true",
                        help="Publish even if a table would lose more than 10%% of its "
                             "current Neon rows for the season.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG,
                        help="Local PostgreSQL connection JSON from postgres_etl.")
    parser.add_argument("--neon-url-env", default=NEON_URL_ENV,
                        help=f"Environment variable holding the Neon URL (default: {NEON_URL_ENV}).")
    return parser


def run_drop_old_names(args):
    neon = neon_connect(args.neon_url_env)
    try:
        print("Mode: " + ("dry run (Neon unchanged)" if args.dry_run
                          else "drop the old etl_flat_* views in Neon"), flush=True)
        print("The web app must already read the app_* names; after this, the old names "
              "no longer exist in Neon.", flush=True)
        drop_old_names(neon, dry_run=args.dry_run)
        return 0
    finally:
        neon.close()


def run(args, names):
    started = time.monotonic()
    local = connect(args.config)
    neon = None
    try:
        local.set_client_encoding("UTF8")
        rename_local_tables(local)
        available = available_seasons(local, args.competition, ["games"])
        local.rollback()
        seasons, missing = select_seasons(args.season_code, args.competition, available)
        if missing:
            print("Not loaded locally; skipping seasons: " + ", ".join(missing), flush=True)
        neon = neon_connect(args.neon_url_env)
        neon.set_client_encoding("UTF8")
        cross_season_tables = RECORDS_TABLES + PLAYER_TABLES
        season_names = [name for name in names if name not in cross_season_tables]
        cross_season_names = [name for name in names if name in cross_season_tables]
        print(f"Competition: {args.competition}", flush=True)
        print(f"Seasons: {', '.join(seasons)}", flush=True)
        print(f"Tables: {len(names)} web-app tables", flush=True)
        print(f"Mode: {'dry run (Neon unchanged)' if args.dry_run else 'publish to Neon'}",
              flush=True)

        if season_names:
            for season_code in seasons:
                season_started = time.monotonic()
                print(f"\nSeason {season_code} | elapsed {elapsed(started)}", flush=True)
                result = publish_season(local, neon, args.competition, season_code, season_names,
                                        dry_run=args.dry_run, allow_shrink=args.allow_shrink)
                for name, (before, after) in result.items():
                    shown = "missing" if before is None else f"{before:,}"
                    verb = "would become" if args.dry_run else "->"
                    print(f"  {physical_name(name)}: {shown} {verb} {after:,} rows", flush=True)
                status = "checked" if args.dry_run else "committed"
                print(f"Season {season_code} {status} in {elapsed(season_started)}", flush=True)

        if cross_season_names:
            # Not season-scoped: always the full local table, independent of -sc.
            print(f"\nCross-season tables (all local history) | elapsed {elapsed(started)}",
                  flush=True)
            result = publish_records(local, neon, cross_season_names,
                                     dry_run=args.dry_run, allow_shrink=args.allow_shrink)
            for name, (before, after) in result.items():
                shown = "missing" if before is None else f"{before:,}"
                verb = "would become" if args.dry_run else "->"
                print(f"  {physical_name(name)}: {shown} {verb} {after:,} rows", flush=True)
            status = "checked" if args.dry_run else "committed"
            print(f"Cross-season tables {status} in {elapsed(started)}", flush=True)

        print(f"\nFinished {len(seasons)} season(s) in {elapsed(started)}", flush=True)
        return 0
    finally:
        local.close()
        if neon is not None:
            neon.close()


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.list_tables:
        for name in APP_TABLES:
            print(f"{name:40} {physical_name(name)}")
        return 0
    if args.drop_old_names and (args.table != ["all"] or args.season_code != ["current"]):
        parser.error("--drop-old-names cannot be combined with --table or --season-code")
    unknown = set(args.table) - {"all", *APP_TABLES}
    if unknown:
        parser.error("Unknown or non-app table(s): " + ", ".join(sorted(unknown)))
    if "all" in args.table and len(args.table) != 1:
        parser.error("'all' must be used alone with --table")
    names = list(APP_TABLES) if args.table == ["all"] else list(dict.fromkeys(args.table))

    log_path = log_directory("neon_publish") / f"logfile_{datetime.now():%Y%m%d_%H%M%S_%f}"
    with log_path.open("w", encoding="utf-8") as log:
        with redirect_stdout(Tee(sys.stdout, log)):
            try:
                if args.drop_old_names:
                    return run_drop_old_names(args)
                return run(args, names)
            except KeyboardInterrupt:
                print("\nInterrupted. The open Neon transaction was rolled back.", flush=True)
                return 130
            except Exception as error:
                print(f"Publish failed (Neon unchanged for the failing season): {error}",
                      flush=True)
                return 1


if __name__ == "__main__":
    sys.exit(main())
