"""Load the bronze layer into season-scoped PostgreSQL tables."""

import argparse
import re
import sys
from pathlib import Path

from advanced import SOURCE_TABLES as ADVANCED_SOURCES, run_seasons as run_advanced
from possessions import TRIGGER_TABLES as POSSESSION_SOURCES, run_seasons as run_possessions
from lineups import run_seasons as run_lineups
from on_court import TRIGGER_TABLES as ON_COURT_SOURCES, run_seasons as run_on_court
from score_flow import run_seasons as run_score_flow
from shot_splits import TRIGGER_TABLES as SHOT_SOURCES, run_seasons as run_shot_splits
from shot_zones import run_seasons as run_shot_zones
from flat_loader import FlatDatabaseLoader
from flat_schema import TABLES as FLAT_TABLES, physical_name
from quality import validate_loaded
from shared import (COMPETITION_CODES as PREFIX, DEFAULT_CONFIG, available_scopes,
                    current_season_year)


HERE = Path(__file__).resolve().parent
DEFAULT_DATA_ROOT = HERE.parent / "data"


def available_seasons(data_root, competition):
    """Seasons with a bronze directory under data/bronze/<competition>."""
    prefix = PREFIX[competition]
    return [
        scope for scope in available_scopes(Path(data_root) / "bronze", competition)
        if re.fullmatch(rf"{prefix}\d{{4}}", scope)
    ]


def requested_seasons(tokens, competition, available, parser):
    prefix = PREFIX[competition]
    if "all" in tokens:
        if len(tokens) != 1:
            parser.error("'all' must be used alone with --season-code")
        requested = set(available)
    elif "latest" in tokens:
        if len(tokens) != 1:
            parser.error("'latest' must be used alone with --season-code")
        requested = {max(available)} if available else set()
    else:
        requested = set()
        for token in tokens:
            if token == "current":
                requested.add(f"{prefix}{current_season_year()}")
                continue
            if re.fullmatch(rf"{prefix}\d{{4}}", token, re.IGNORECASE):
                requested.add(token.upper())
                continue
            if re.fullmatch(r"\d{4}", token):
                requested.add(f"{prefix}{token}")
                continue
            match = re.fullmatch(r"(\d{4})-(\d{4})", token)
            if match:
                first, last = map(int, match.groups())
                if first > last:
                    parser.error(f"Season range must ascend: {token}")
                requested.update(f"{prefix}{year}" for year in range(first, last + 1))
                continue
            parser.error(f"Invalid season code or range: {token}")
    missing = sorted(requested - set(available))
    if missing:
        print("Not cached locally; skipping: " + ", ".join(missing), flush=True)
    selected = sorted(requested & set(available))
    if not selected:
        parser.error(
            f"No requested {competition} raw seasons are available. "
            f"Available: {', '.join(available) or '(none)'}"
        )
    return selected


def build_parser():
    parser = argparse.ArgumentParser(
        description="Load the bronze layer into PostgreSQL. No API requests are made."
    )
    parser.add_argument("-cp", "--competition", choices=PREFIX, default="euroleague",
                        help="Competition to load (default: euroleague).")
    parser.add_argument("-sc", "--season-code", nargs="+", default=["latest"],
                        help="Years, codes, inclusive ranges, 'current', 'latest', or 'all'. "
                             "Default: latest locally cached season.")
    parser.add_argument("-tb", "--table", nargs="+", default=["all"],
                        help="Tables to load; default: all. Use --list-tables for names.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Read and validate rows without connecting to PostgreSQL.")
    parser.add_argument("--quality-only", action="store_true",
                        help="Check already-loaded flat tables without loading or changing rows.")
    parser.add_argument("--skip-quality-check", action="store_true",
                        help="Skip the default read-only checks after loading flat tables.")
    parser.add_argument("--list-tables", action="store_true",
                        help="List available table names and exit.")
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT,
                        help="Data directory containing bronze/<competition>/.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG,
                        help="PostgreSQL connection JSON; unused in --dry-run mode.")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.quality_only and (args.dry_run or args.skip_quality_check):
        parser.error("--quality-only cannot be combined with --dry-run or --skip-quality-check")
    if args.list_tables:
        print("\n".join(FLAT_TABLES))
        return 0
    unknown = set(args.table) - {"all", *FLAT_TABLES}
    if unknown:
        parser.error("Unknown table(s): " + ", ".join(sorted(unknown)))
    available = available_seasons(args.data_root, args.competition)
    seasons = requested_seasons(args.season_code, args.competition, available, parser)
    tables = list(FLAT_TABLES) if "all" in args.table else list(dict.fromkeys(args.table))
    print(f"Competition: {args.competition}")
    print(f"Seasons: {', '.join(seasons)}")
    print(f"Tables: {', '.join(physical_name(name) for name in tables)}")
    mode = "quality check only" if args.quality_only else (
        "dry run" if args.dry_run else "PostgreSQL load"
    )
    print(f"Mode: {mode}", flush=True)
    loader = FlatDatabaseLoader(args.data_root, args.competition, seasons,
                                tables, args.config, args.dry_run)
    try:
        if not args.quality_only:
            loader.run()
        if not (args.quality_only or args.dry_run) and set(tables) & set(ADVANCED_SOURCES):
            print("\nPer-game advanced stats", flush=True)
            if not run_advanced(args.config, args.competition, seasons):
                print("Advanced stats checks failed; inspect the reported issues.",
                      file=sys.stderr, flush=True)
                return 1
        if not (args.quality_only or args.dry_run) and set(tables) & set(POSSESSION_SOURCES):
            print("\nCounted possessions", flush=True)
            if not run_possessions(args.config, args.competition, seasons):
                print("Counted possession checks failed; inspect the reported issues.",
                      file=sys.stderr, flush=True)
                return 1
            print("\nScore flow", flush=True)
            if not run_score_flow(args.config, args.competition, seasons):
                print("Score flow checks failed; inspect the reported issues.",
                      file=sys.stderr, flush=True)
                return 1
        if not (args.quality_only or args.dry_run) and set(tables) & set(ON_COURT_SOURCES):
            print("\nOn-court intervals", flush=True)
            if not run_on_court(args.config, args.competition, seasons):
                print("On-court checks failed; inspect the reported issues.",
                      file=sys.stderr, flush=True)
                return 1
            print("\nLineup stints", flush=True)
            if not run_lineups(args.config, args.competition, seasons):
                print("Lineup stint checks failed; inspect the reported issues.",
                      file=sys.stderr, flush=True)
                return 1
        if not (args.quality_only or args.dry_run) and set(tables) & set(SHOT_SOURCES):
            for label, run in (("Shot splits", run_shot_splits),
                               ("Shot zones", run_shot_zones)):
                print(f"\n{label}", flush=True)
                if not run(args.config, args.competition, seasons):
                    print(f"{label} checks failed; inspect the reported issues.",
                          file=sys.stderr, flush=True)
                    return 1
        if args.quality_only or (not args.dry_run and not args.skip_quality_check):
            print("\nRead-only quality checks", flush=True)
            passed = True
            passed &= validate_loaded(args.config, args.data_root, args.competition,
                                      seasons, tables)
            if not passed:
                print("Quality checks failed. Loaded rows were not rolled back; "
                      "inspect the reported issues.", file=sys.stderr, flush=True)
                return 1
    except (OSError, ValueError, RuntimeError) as error:
        print(f"ETL failed: {error}", file=sys.stderr, flush=True)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted. The active table transaction was rolled back; "
              "rerun the same command to resume.", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
