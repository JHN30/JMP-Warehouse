"""Refresh one season end to end: fetch -> load local PostgreSQL -> publish to Neon.

Run it from the VS Code terminal whenever you want (for example nightly and
after each round). When the API returned nothing new and no earlier publish is
pending, the run stops after the fetch and Neon is left untouched. Every run
writes one log file to logs/refresh/ and ends with a summary.

    python pipeline.py                     # current EuroLeague season
    python pipeline.py --dry-run-publish   # everything, but Neon only compared
    python pipeline.py -sc 2025
"""

import argparse
import getpass
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from common.db import log_directory
from common.seasons import COMPETITION_CODES, current_season_year


ROOT = Path(__file__).resolve().parent
NEON_URL_ENV = "NEON_DATABASE_URL"
CHILD_ENV = {"PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}


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


class RunLog:
    """Show every line on the console and keep it in one UTF-8 log file."""

    def __init__(self, path, console=None):
        self.path = Path(path)
        self.console = console or sys.stdout
        self.file = self.path.open("w", encoding="utf-8")

    def line(self, text=""):
        self.file.write(text + "\n")
        self.file.flush()
        try:
            self.console.write(text + "\n")
        except UnicodeEncodeError:
            encoding = getattr(self.console, "encoding", None) or "ascii"
            self.console.write(text.encode(encoding, "replace").decode(encoding) + "\n")
        self.console.flush()

    def close(self):
        self.file.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def run_stage(command, cwd, env, emit):
    """Run one stage, streaming its merged output line by line; return its exit code."""
    process = subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT)
    try:
        for raw in process.stdout:
            emit(raw.decode("utf-8", "replace").rstrip("\r\n"))
    finally:
        process.stdout.close()
    return process.wait()


@dataclass
class StageFacts:
    """What the summary reports; None means the stage did not run."""
    changed: int | None = None
    failed_requests: int | None = None
    load_lines: list = field(default_factory=list)
    publish_lines: list = field(default_factory=list)


def load_facts(lines):
    rows = quality = None
    issues, failure = [], None
    for text in lines:
        if match := re.match(r"Finished: ([\d,]+) rows", text):
            rows = match.group(1)
        elif match := re.match(r"Quality \S+: .*?(\d+) error\(s\), (\d+) warning\(s\)", text):
            errors, warnings = (int(value) for value in match.groups())
            quality = (quality[0] + errors, quality[1] + warnings) if quality else (errors, warnings)
        elif match := re.match(r"\s+((?:WARN|ERROR) .+)$", text):
            issues.append(match.group(1))
        elif text.startswith(("ETL failed:", "Quality checks failed")):
            failure = failure or text
    return rows, quality, issues, failure


def publish_facts(lines):
    tables, mode, failure = [], None, None
    for text in lines:
        if match := re.match(r"\s+(\S+): (missing|[\d,]+) (->|would become) ([\d,]+) rows$", text):
            tables.append(f"{match.group(1)}: {match.group(2)} -> {match.group(4)}")
        elif match := re.match(r"Season \S+ (committed|checked)", text):
            mode = "committed" if match.group(1) == "committed" else "dry run (Neon unchanged)"
        elif text.startswith("Publish failed"):
            failure = failure or text
    return tables, mode, failure


def build_summary(season_code, result, facts, seconds, log_path, next_step=None):
    """Return the summary lines. A stage that did not run shows as 'not run', never 0."""
    minutes, secs = divmod(int(seconds), 60)
    lines = ["", "=" * 25 + " Refresh summary " + "=" * 25,
             f"Result:   {result}",
             f"Season:   {season_code}    Time: {minutes} min {secs:02d} s"]
    if facts.changed is None:
        lines.append("Fetch:    not run")
    else:
        lines.append(f"Fetch:    {facts.changed} changed resource(s), "
                     f"{facts.failed_requests} failed request(s)")
    if not facts.load_lines:
        lines.append("Load:     not run")
    else:
        rows, quality, issues, failure = load_facts(facts.load_lines)
        quality_text = (f"quality {quality[0]} error(s), {quality[1]} warning(s)"
                        if quality else "quality not run")
        rows_text = (f"{rows} rows loaded" if rows
                     else "rows loaded unknown (the load did not finish)")
        lines.append(f"Load:     {rows_text}; {quality_text}")
        lines.extend(f"            {issue}" for issue in issues)
        if failure:
            lines.append(f"            {failure}")
    if not facts.publish_lines:
        lines.append("Publish:  not run")
    else:
        tables, mode, failure = publish_facts(facts.publish_lines)
        lines.append(f"Publish:  {mode or 'not completed'}")
        lines.extend(f"            {table}" for table in tables)
        if failure:
            lines.append(f"            {failure}")
    lines.append(f"Log:      {log_path}")
    if next_step:
        lines.append(f"Next:     {next_step}")
    lines.append("=" * 67)
    return lines


def unquote(value):
    """Strip whitespace and one pair of surrounding quotes, as pasted from a .env line."""
    value = (value or "").strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1].strip()
    return value


def resolve_neon_url(environ, prompt, interactive):
    """Return (url, source). The URL is kept in memory for this run only."""
    url = unquote(environ.get(NEON_URL_ENV))
    if url:
        return url, f"from {NEON_URL_ENV}"
    if not interactive:
        return None, "no interactive console to ask"
    url = unquote(prompt("Neon URL (hidden, used for this run only): "))
    return (url, "entered at the prompt") if url else (None, "nothing entered")


def looks_like_postgres_url(url):
    """True for postgres[ql]://user:password@host/... ; a malformed URL is refused
    before publishing, because the driver's error message would echo it."""
    try:
        parts = urlsplit(url)
        return (parts.scheme in ("postgres", "postgresql") and bool(parts.hostname)
                and bool(parts.password))
    except ValueError:
        return False


def redactor(url):
    """Return a function that hides the URL and its credentials in a line of output.

    A connection error can echo part of the URL, including the password, so every
    publish-stage line passes through this before it is shown or logged. The
    credentials are also taken from the raw text between :// and @, so they are
    hidden even when the URL does not parse.
    """
    secrets = {url}
    try:
        password = urlsplit(url).password
    except ValueError:
        password = None
    if password:
        secrets.add(password)
    if match := re.search(r"://([^@\s]+)@", url):
        userinfo = match.group(1)
        secrets.add(userinfo)
        if ":" in userinfo:
            secrets.add(userinfo.split(":", 1)[1])
    ordered = sorted((secret for secret in secrets if secret), key=len, reverse=True)

    def redact(text):
        for secret in ordered:
            text = text.replace(secret, "***")
        return text
    return redact


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


def refresh(args, season_code, log, state_file, facts, stage_runner=run_stage,
            prompt=getpass.getpass, environ=None, interactive=None):
    """Run the stages, filling ``facts`` as they go; return (exit code, result, next step)."""
    environ = os.environ if environ is None else environ
    interactive = sys.stdin.isatty() if interactive is None else interactive
    python = sys.executable
    child_env = dict(environ, **CHILD_ENV)

    def stage(title, command, into=None, cwd=ROOT, env=child_env, redact=None):
        log.line(f"\n=== {title}: {' '.join(command[1:])}")

        def emit(text):
            if redact is not None:
                text = redact(text)
            log.line(text)
            if into is not None:
                into.append(text)
        return stage_runner(command, cwd, env, emit)

    log.line(f"Pipeline {args.competition} {season_code} started {datetime.now():%Y-%m-%d %H:%M:%S}")

    if not args.skip_fetch:
        with tempfile.TemporaryDirectory() as temporary:
            summary_path = Path(temporary) / "fetch_summary.json"
            code = stage("Fetch", [
                python, "main.py", "-cp", args.competition, "-sc", season_code[1:],
                "--hot-hours", str(args.hot_hours),
                "--request-interval", str(args.request_interval),
                "--summary-file", str(summary_path),
            ], cwd=ROOT / "api_requests")
            if code != 0:
                return (code, f"FAILED at Fetch (exit {code})",
                        "Nothing was loaded or published. Check the log, then run again.")
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        changed = [resource for resource in summary["changed_resources"]
                   if not resource.startswith("_catalog/")]
        facts.changed, facts.failed_requests = len(changed), summary["failed_requests"]
        log.line(f"Fetch: {len(changed)} changed resource(s), "
                 f"{summary['failed_requests']} failed request(s).")
        if changed:
            write_state(state_file, publish_pending=True, last_change_count=len(changed))

    pending = read_state(state_file).get("publish_pending", False)
    if not (pending or args.force or args.skip_fetch):
        log.line("Nothing changed and no publish is pending; Neon left as is.")
        return 0, "NOTHING TO DO", None

    code = stage("Load local PostgreSQL",
                 [python, "postgres_etl/main.py", "-cp", args.competition, "-sc", season_code],
                 into=facts.load_lines)
    if code != 0:
        return (code, f"FAILED at Load (exit {code})",
                "Neon was NOT updated; the publish stays pending for the next run. "
                "Fix the reported problem (see the log), then run again.")

    url, source = resolve_neon_url(environ, prompt, interactive)
    if not url:
        log.line(f"No Neon URL ({source}); not publishing.")
        return (1, "STOPPED before Publish (no Neon URL)",
                f"The local database is up to date; the publish stays pending. Set "
                f"{NEON_URL_ENV} or enter the URL when asked, then run again.")
    if not looks_like_postgres_url(url):
        log.line(f"The Neon URL ({source}) is not a postgresql://user:password@host/... URL; "
                 "not publishing. Check it for stray or curly quotes.")
        return (1, "STOPPED before Publish (Neon URL is malformed)",
                "The local database is up to date; the publish stays pending. Fix the URL "
                f"({NEON_URL_ENV} or the prompt), then run again.")
    log.line(f"Neon URL: {source}.")

    publish_command = [python, "neon_publish/main.py", "-cp", args.competition,
                       "-sc", season_code]
    if args.dry_run_publish:
        publish_command.append("--dry-run")
    if args.allow_shrink:
        publish_command.append("--allow-shrink")
    code = stage("Publish to Neon", publish_command, into=facts.publish_lines,
                 env=dict(child_env, **{NEON_URL_ENV: url}), redact=redactor(url))
    if code != 0:
        return (code, f"FAILED at Publish (exit {code})",
                "Neon keeps its previous rows; the publish stays pending for the next run. "
                "See the log for the reason.")

    if args.dry_run_publish:
        return 0, "OK (dry run)", "Nothing was written to Neon; the publish stays pending."
    write_state(state_file, publish_pending=False,
                last_published_at_utc=datetime.now(timezone.utc).isoformat())
    return 0, "OK", None


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        season_code = season_code_for(args.competition, args.season_code)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    log_path = log_directory("refresh") / f"refresh_{datetime.now():%Y%m%d_%H%M%S}.log"
    started = time.monotonic()
    facts = StageFacts()
    with RunLog(log_path) as log:
        try:
            code, result, next_step = refresh(
                args, season_code, log, state_path(args.competition, season_code), facts)
        except KeyboardInterrupt:
            code, result = 130, "INTERRUPTED (Ctrl+C)"
            next_step = "Run again; finished downloads and committed publishes are kept."
        shown = log_path.relative_to(ROOT) if log_path.is_relative_to(ROOT) else log_path
        for text in build_summary(season_code, result, facts, time.monotonic() - started,
                                  shown, next_step):
            log.line(text)
    return code


if __name__ == "__main__":
    sys.exit(main())
