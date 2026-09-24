"""Refresh one season end to end: fetch -> load local PostgreSQL -> publish to Neon.

Safe to run as often as wanted (nightly, and every couple of hours on game
days). When the API returned nothing new and no earlier publish is pending,
the run stops after the fetch and Neon is left untouched.

    python pipeline.py                     # current EuroLeague season
    python pipeline.py -sc 2026 --dry-run-publish
"""

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from common.seasons import COMPETITION_CODES, current_season_year


ROOT = Path(__file__).resolve().parent


def season_code_for(competition, token):
    prefix = COMPETITION_CODES[competition]
    if token == "current":
        return f"{prefix}{current_season_year()}"
    token = token.upper()
    if token.isdigit() and len(token) == 4:
        return f"{prefix}{token}"
    if len(token) == 5 and token[0] == prefix and token[1:].isdigit():
        return token
    raise ValueError(f"Expected current, YYYY or {prefix}YYYY, got {token!r}")


def state_path(competition, season_code):
    return ROOT / "data" / "state" / f"pipeline_{competition}_{season_code}.json"


def read_state(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write_state(path, **values):
    path.parent.mkdir(parents=True, exist_ok=True)
    state = read_state(path)
    state.update(values, updated_at_utc=datetime.now(timezone.utc).isoformat())
    path.write_text(json.dumps(state, indent=1), encoding="utf-8")


def step(title, command, cwd=ROOT):
    print(f"\n=== {title}: {' '.join(command[1:])}", flush=True)
    return subprocess.run(command, cwd=cwd).returncode


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-cp", "--competition", choices=COMPETITION_CODES, default="euroleague")
    parser.add_argument("-sc", "--season-code", default="current",
                        help="current (default), a start year such as 2026, or E2026.")
    parser.add_argument("--force", action="store_true",
                        help="Load and publish even if the fetch changed nothing.")
    parser.add_argument("--skip-fetch", action="store_true",
                        help="Use the existing raw cache; implies --force.")
    parser.add_argument("--dry-run-publish", action="store_true",
                        help="Compare row counts with Neon instead of publishing.")
    parser.add_argument("--allow-shrink", action="store_true",
                        help="Passed to the publisher: allow a table to lose more than 10%% "
                             "of its Neon rows (only after checking why).")
    parser.add_argument("--hot-hours", type=float, default=48,
                        help="Passed to the fetcher; see api_requests --hot-hours.")
    parser.add_argument("--request-interval", type=float, default=2.5,
                        help="Passed to the fetcher; minimum seconds between API requests.")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        season_code = season_code_for(args.competition, args.season_code)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2
    python = sys.executable
    state_file = state_path(args.competition, season_code)
    print(f"Pipeline {args.competition} {season_code} started "
          f"{datetime.now():%Y-%m-%d %H:%M:%S}", flush=True)

    if not args.skip_fetch:
        with tempfile.TemporaryDirectory() as temporary:
            summary_path = Path(temporary) / "fetch_summary.json"
            code = step("Fetch", [
                python, "main.py", "-cp", args.competition, "-sc", season_code[1:],
                "--hot-hours", str(args.hot_hours),
                "--request-interval", str(args.request_interval),
                "--summary-file", str(summary_path),
            ], cwd=ROOT / "api_requests")
            if code != 0:
                print(f"Fetch failed with exit code {code}; nothing loaded or published.")
                return code
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        changed = [resource for resource in summary["changed_resources"]
                   if not resource.startswith("_catalog/")]
        print(f"Fetch: {len(changed)} changed resource(s), "
              f"{summary['failed_requests']} failed request(s).", flush=True)
        if changed:
            write_state(state_file, publish_pending=True, last_change_count=len(changed))

    pending = read_state(state_file).get("publish_pending", False)
    if not (pending or args.force or args.skip_fetch):
        print("Nothing changed and no publish is pending; Neon left as is.")
        return 0

    code = step("Load local PostgreSQL",
                [python, "postgres_etl/main.py", "-cp", args.competition, "-sc", season_code])
    if code != 0:
        print(f"Load or quality checks failed (exit {code}); Neon NOT updated. "
              "The publish stays pending for the next run.")
        return code

    publish_command = [python, "neon_publish/main.py", "-cp", args.competition,
                       "-sc", season_code]
    if args.dry_run_publish:
        publish_command.append("--dry-run")
    if args.allow_shrink:
        publish_command.append("--allow-shrink")
    code = step("Publish to Neon", publish_command)
    if code != 0:
        print(f"Publish failed (exit {code}); Neon keeps its previous rows. "
              "The publish stays pending for the next run.")
        return code

    if not args.dry_run_publish:
        write_state(state_file, publish_pending=False,
                    last_published_at_utc=datetime.now(timezone.utc).isoformat())
    print(f"\nPipeline {season_code} finished.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
