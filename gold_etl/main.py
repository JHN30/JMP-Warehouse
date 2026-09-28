"""Build local Gold source and derived tables from already-loaded Silver."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.db import DEFAULT_CONFIG, connect  # noqa: E402
from common.seasons import COMPETITION_CODES, select_seasons  # noqa: E402
from gold_etl.loader import replace_scope  # noqa: E402
from gold_etl.loader import replace_postseason_scope  # noqa: E402
from gold_etl.loader import replace_standings_scope  # noqa: E402
from gold_etl.loader import read_aggregate_rows, replace_aggregate_scope  # noqa: E402
from gold_etl.loader import replace_records_scope, replace_series_scope, replace_identity_scope  # noqa: E402
from gold_etl.records import read_rows as read_record_rows  # noqa: E402
from gold_etl.identity import read_rows as read_identity_rows  # noqa: E402
from gold_etl.series import read_rows as read_series_rows  # noqa: E402
from gold_etl.postseason import TABLES as PS_TABLES, read_rows as read_postseason_rows  # noqa: E402
from gold_etl.standings import read_rows as read_standings_rows  # noqa: E402
from gold_etl.quality import (check_scope, check_postseason_scope,
                              check_standings_scope, check_aggregate_scope,
                              check_records_scope, check_series_scope,
                              check_identity_scope)  # noqa: E402
from gold_etl.schema import (AGGREGATE_NAMES, DERIVED_NAMES, IDENTITY_TABLES, RECORDS_TABLES,
                             SOURCE_NAMES, count_sql)  # noqa: E402


def build_parser():
    parser = argparse.ArgumentParser(description="Build local Gold tables from Silver.")
    parser.add_argument("-cp", "--competition", choices=COMPETITION_CODES,
                        default="euroleague")
    parser.add_argument("-sc", "--season-code", nargs="+", default=["latest"],
                        help="Years, codes, ranges, current, latest, or all in local Silver.")
    parser.add_argument("-tb", "--table", nargs="+", default=["all"],
                        help="Gold tables; default all.")
    parser.add_argument("--list-tables", action="store_true")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show source and derived row counts without Gold writes.")
    parser.add_argument("--quality-only", action="store_true",
                        help="Compare Gold rows with Silver without writes.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    return parser


def available_seasons(cursor, competition_code):
    cursor.execute('SELECT season_code FROM silver."seasons" '
                   'WHERE competition_code = %s ORDER BY season_code',
                   (competition_code,))
    return [row[0] for row in cursor.fetchall()]


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.list_tables:
        print("\n".join((*SOURCE_NAMES, *DERIVED_NAMES)))
        return 0
    if args.dry_run and args.quality_only:
        parser.error("--dry-run and --quality-only cannot be combined")
    unknown = set(args.table) - {"all", *SOURCE_NAMES, *DERIVED_NAMES}
    if unknown:
        parser.error("Unknown table(s): " + ", ".join(sorted(unknown)))
    if "all" in args.table and len(args.table) != 1:
        parser.error("'all' must be used alone with --table")
    tables = (*SOURCE_NAMES, *DERIVED_NAMES) if args.table == ["all"] else tuple(dict.fromkeys(args.table))
    if args.competition == "eurocup" and any(name in RECORDS_TABLES for name in tables):
        parser.error("EuroCup records are not supported; select non-record tables")
    connection = None
    try:
        connection = connect(args.config)
        if args.dry_run or args.quality_only:
            connection.set_session(readonly=True, isolation_level="REPEATABLE READ")
        with connection.cursor() as cursor:
            available = available_seasons(cursor, COMPETITION_CODES[args.competition])
        seasons, missing = select_seasons(args.season_code, args.competition, available)
        if missing:
            print("Not loaded in Silver; skipping: " + ", ".join(missing), flush=True)
        print(f"Competition: {args.competition}")
        print(f"Seasons: {', '.join(seasons)}")
        print(f"Tables: {', '.join(tables)}")
        if any(name in RECORDS_TABLES for name in tables):
            print("Records scope: all locally loaded EuroLeague seasons", flush=True)
        if any(name in IDENTITY_TABLES for name in tables):
            print("Identity scope: all locally loaded Silver seasons", flush=True)
        print("Mode: " + ("read-only dry run" if args.dry_run else
                          "read-only quality check" if args.quality_only else "Gold load"),
              flush=True)
        passed = True
        for season in seasons:
            for name in tables:
                scope = (COMPETITION_CODES[args.competition], season)
                if name in RECORDS_TABLES or name in IDENTITY_TABLES:
                    continue
                if name == "app_postseason_series":
                    if args.dry_run:
                        with connection.cursor() as cursor:
                            count = len(read_series_rows(cursor, *scope))
                        print(f"gold.{name} {season}: {count} derived rows", flush=True)
                    elif args.quality_only:
                        with connection.cursor() as cursor:
                            issues = check_series_scope(cursor, *scope)
                        for issue in issues:
                            print(issue, file=sys.stderr, flush=True)
                        passed &= not issues
                    else:
                        count = replace_series_scope(connection, *scope)
                        print(f"gold.{name} {season}: {count} rows", flush=True)
                    continue
                if name == "app_standings":
                    if args.dry_run:
                        with connection.cursor() as cursor:
                            count = len(read_standings_rows(cursor, *scope))
                        print(f"gold.app_standings {season}: {count} derived rows", flush=True)
                    elif args.quality_only:
                        with connection.cursor() as cursor:
                            issues = check_standings_scope(cursor, *scope)
                        for issue in issues:
                            print(issue, file=sys.stderr, flush=True)
                        passed &= not issues
                    else:
                        count = replace_standings_scope(connection, *scope)
                        print(f"gold.app_standings {season}: {count} rows", flush=True)
                    continue
                if name in AGGREGATE_NAMES:
                    if args.dry_run:
                        with connection.cursor() as cursor:
                            count = len(read_aggregate_rows(cursor, name, *scope))
                        print(f"gold.{name} {season}: {count} derived rows", flush=True)
                    elif args.quality_only:
                        with connection.cursor() as cursor:
                            issues = check_aggregate_scope(cursor, name, *scope)
                        for issue in issues:
                            print(issue, file=sys.stderr, flush=True)
                        passed &= not issues
                    else:
                        count = replace_aggregate_scope(connection, name, *scope)
                        print(f"gold.{name} {season}: {count} rows", flush=True)
                    continue
                if args.dry_run:
                    with connection.cursor() as cursor:
                        cursor.execute(count_sql(name, "silver"), scope)
                        count = cursor.fetchone()[0]
                    print(f"silver.{name} {season}: {count} source rows", flush=True)
                    if name in PS_TABLES:
                        with connection.cursor() as cursor:
                            derived = len(read_postseason_rows(cursor, *scope)[name])
                        print(f"gold.{name} PS {season}: {derived} derived rows", flush=True)
                elif args.quality_only:
                    with connection.cursor() as cursor:
                        issues = check_scope(cursor, name, *scope)
                        if name in PS_TABLES:
                            issues += check_postseason_scope(cursor, name, *scope)
                    for issue in issues:
                        print(issue, file=sys.stderr, flush=True)
                    passed &= not issues
                else:
                    count = replace_scope(connection, name, *scope)
                    print(f"gold.{name} {season}: {count} rows", flush=True)
                    if name in PS_TABLES:
                        derived = replace_postseason_scope(connection, name, *scope)
                        print(f"gold.{name} PS {season}: {derived} derived rows", flush=True)
        for name in tables:
            if name not in RECORDS_TABLES:
                continue
            competition_code = COMPETITION_CODES[args.competition]
            if args.dry_run:
                with connection.cursor() as cursor:
                    count = len(read_record_rows(cursor, name, competition_code))
                print(f"gold.{name} all seasons: {count} derived rows", flush=True)
            elif args.quality_only:
                with connection.cursor() as cursor:
                    issues = check_records_scope(cursor, name, competition_code)
                for issue in issues:
                    print(issue, file=sys.stderr, flush=True)
                passed &= not issues
            else:
                count = replace_records_scope(connection, name, competition_code)
                print(f"gold.{name} all seasons: {count} rows", flush=True)
        for name in tables:
            if name not in IDENTITY_TABLES:
                continue
            competition_code = COMPETITION_CODES[args.competition]
            if args.dry_run:
                with connection.cursor() as cursor:
                    count = len(read_identity_rows(cursor, name, competition_code))
                print(f"gold.{name} all seasons: {count} derived rows", flush=True)
            elif args.quality_only:
                with connection.cursor() as cursor:
                    issues = check_identity_scope(cursor, name, competition_code)
                for issue in issues:
                    print(issue, file=sys.stderr, flush=True)
                passed &= not issues
            else:
                count = replace_identity_scope(connection, name, competition_code)
                print(f"gold.{name} all seasons: {count} rows", flush=True)
        if args.quality_only:
            print("Gold quality: passed" if passed else "Gold quality: failed", flush=True)
            return 0 if passed else 1
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Gold ETL failed: {error}", file=sys.stderr, flush=True)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted. Active scope was rolled back.", file=sys.stderr)
        return 130
    finally:
        if connection is not None:
            connection.close()


if __name__ == "__main__":
    sys.exit(main())
