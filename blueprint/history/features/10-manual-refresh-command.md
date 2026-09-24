# Feature: Manual refresh command

**From build-plan:** feature 10
**Build attempt:** 1
**Status:** verified
**Branch:** feature/manual-refresh-command

## Goal

Give the owner one command to run whenever they want: it refreshes the current
EuroLeague season end to end (fetch, load, quality checks, publish), asks for the
Neon URL safely only when it is needed, writes one log file for the whole run,
and ends with a short summary that says clearly whether the run succeeded.
Automatic scheduling is feature 20.

## In scope

- `pipeline.py` stays the one command. It gains: one run log per refresh, a
  final summary, and safe Neon URL handling. Existing options (`-sc`,
  `--force`, `--skip-fetch`, `--dry-run-publish`, `--allow-shrink`) keep
  working as today.
- Run from the VS Code terminal: `python pipeline.py` (typed), or the VS Code
  tasks "Refresh current season" and "Refresh current season (dry run)" in
  `.vscode/tasks.json` (Terminal > Run Task), which run the same command in the
  integrated terminal.
- The command written down where the owner looks: a "Run a refresh" section at
  the top of `README.md`, and the `AGENTS.md` Commands section.

## Out of scope

- Windows Task Scheduler, GitHub Actions or any other automatic trigger (feature 20).
- A local-only mode that skips publishing, extra notifications (toast, email),
  or a separate "last run" status file.
- A double-click launcher (`.cmd`) or a PowerShell script: the owner runs it
  from the VS Code terminal.
- Changes to what fetch, load or publish do, or to their own logs.

## Build loop

- `workflow.stepReview` is `feature`: build all steps, then one review packet,
  followed by the optional code walkthrough.
- `workflow.checkpointCommits` is `disabled`: no step commits. `/complete`
  creates the feature commit (no AI attribution).
- Tests are a gate: the three test commands in `AGENTS.md` must pass before
  review and before `/complete`.

## Build steps

- [x] 1. **Run log and streamed output.** In `pipeline.py`, run each stage so its
  output is shown live on the console and also written, with the pipeline's own
  messages, to one UTF-8 log file `logs/refresh/refresh_<YYYYMMDD_HHMMSS>.log`
  (created via `common.db.log_directory("refresh")`). Child processes run with
  `PYTHONIOENCODING=utf-8`; the parent decodes UTF-8 with replacement and never
  crashes on characters the console cannot show. Stage exit codes and the
  existing skip / pending logic stay exactly as today.
  Done when: tests with a fake stage prove every stage line reaches both the
  console stream and the log file, and a failing stage still stops the run with
  its exit code.

- [x] 2. **Final summary.** After the run (success, nothing-to-do, or failure),
  print and log a summary block built from the stage output:
  - Result: `OK`, `NOTHING TO DO` (fetch changed nothing, no pending publish),
    `OK (dry run)`, or `FAILED at <stage> (exit N)`, plus what happens next on
    failure (the publish stays pending; see the log).
  - Fetch: changed resources and failed requests.
  - Load: rows loaded, quality errors and warnings, and each warning line.
  - Publish: each table `before -> after` rows, and committed or dry run.
  - Season, total time, and the log file path.
  A value missing from the output (for example a stage that did not run) is
  shown as "not run", never as 0.
  Done when: unit tests feed recorded sample outputs of each stage (success,
  nothing changed, load failure, publish failure, dry run) to the summary
  builder and assert the result lines.

- [x] 3. **Safe Neon URL.** Just before the publish stage (never earlier, so a
  run with nothing to publish never asks), use `NEON_DATABASE_URL` from the
  environment when set. Otherwise ask for it with a hidden prompt
  (`getpass`), for this run only. Pass it to the publish subprocess through its
  environment only; never print it, log it, or write it to a file. An empty
  answer, or no interactive console, stops before publishing with a clear
  message; the publish stays pending, exit code 1.
  Done when: tests with an injected prompt cover env var present (no prompt),
  prompt used, and empty answer (publish not run, pending kept), and a test
  asserts the URL text never appears in the log file.

- [x] 4. **VS Code tasks and docs.** Add `.vscode/tasks.json` with two shell
  tasks run from the workspace folder in the integrated terminal:
  "Refresh current season" (`python pipeline.py`) and "Refresh current season
  (dry run)" (`python pipeline.py --dry-run-publish`). Add a "Run a refresh"
  section at the top of `README.md` and update the `AGENTS.md` Commands section:
  the command, both tasks, the options (`-sc`, `--dry-run-publish`,
  `--allow-shrink`, `--force`, `--skip-fetch`), the log location, what the
  summary shows, and how to set `NEON_DATABASE_URL` as a user environment
  variable (optional; otherwise the command asks).
  Done when: `.vscode/tasks.json` parses as JSON with both tasks, `python
  pipeline.py --help` lists the options, and the README section shows the
  command. Running a task from Terminal > Run Task is the owner's check.

- [x] 5. **Review repairs (F-04, F-05, F-06).** F-04: strip one pair of surrounding
  quotes from the Neon URL (environment or prompt); refuse a URL that is not
  `postgres[ql]://user:password@host/...` before publishing (stop with a message
  that never shows it, publish stays pending), so the driver never echoes a
  malformed URL; and pass every publish-stage line through a redactor that
  replaces the URL, its password and the raw text between `://` and `@` with
  `***` before it reaches the console, the log or the summary. F-05: when the load did
  not finish, the summary says the rows loaded are unknown instead of "no rows".
  F-06: the README tells the owner to set `NEON_DATABASE_URL` in the Windows
  "Edit environment variables for your account" dialog, not with a typed
  command that would stay in the PowerShell history.
  Done when: tests prove a quoted URL is unquoted, a malformed URL (stray or
  curly quotes) is refused before publish without being shown, a fake publish
  stage that prints the URL and password leaves neither in the log or summary,
  and a failed
  load's summary says "unknown"; the three test commands pass.

## Files / areas

- `pipeline.py` - streamed stages, run log, summary, Neon URL handling
- `common/db.py` - reuse `log_directory` (no change expected)
- `neon_publish/tests/test_publish.py` - existing `PipelineTests` class; new tests go here
- `.vscode/tasks.json` - new, two refresh tasks
- `README.md`, `AGENTS.md` - "Run a refresh" section and Commands

## Data / contracts

- Command: `python pipeline.py [existing options]` in the VS Code terminal, or the
  two VS Code tasks.
  Exit codes unchanged: 0 success or nothing to do, the failing stage's code on
  failure, 1 when the Neon URL is missing, 130 on Ctrl+C, 2 for a bad season.
- Log file: `logs/refresh/refresh_<YYYYMMDD_HHMMSS>.log`, UTF-8, the whole run's
  console output plus the summary. `logs/` is git-ignored. Never contains the
  Neon URL.
- Pending-publish state in `data/state/` keeps today's behaviour.
- The summary reads these existing stage lines (no stage output changes):
  `Changed resources: N  ---  Failed requests: M` (fetch),
  `Finished: N rows ...` and `Quality <season>: ... N error(s), M warning(s)`
  plus `  WARN ...` / `  ERROR ...` lines (load),
  `  <table>: <before> -> <after> rows` or `... would become ...` and
  `Season <code> committed|checked ...` (publish).

## Testing

- Test command gate: the three commands in `AGENTS.md`.
- Unit tests (in `PipelineTests`): streaming to console and log, summary for each
  outcome from recorded sample stage output, Neon URL handling with an injected
  prompt and environment, URL never in the log.
- No unit test calls the EuroLeague API, a real database, or Neon.
- Real-run evidence is the owner's: the "Refresh current season (dry run)" task
  (or `python pipeline.py --dry-run-publish`) with their Neon URL during
  `/check`. It is not claimed by this feature's tests.

## Notes for the AI

- Keep it in `pipeline.py` and the standard library (`subprocess`, `getpass`,
  `sys`, `time`); no new dependency, launcher or PowerShell script. VS Code task
  terminals are interactive, so the hidden prompt works there.
- Make the stage runner and the prompt injectable (for example a
  `run_stage` callable and a `prompt` argument) so tests need no real subprocess
  or console.
- Parse only the listed lines, tolerating extra output; unknown lines are ignored.
- On a non-interactive stdin, do not call `getpass`; stop with the message instead.
- Nothing in this feature may call the API, load the database or touch Neon.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":8751,"specSha256":"9b5bff8fedaa05cbf907e97100ee557b3bdc1fc935bdadca7addc894668dae30","branch":"refs/heads/feature/manual-refresh-command","head":"ca4598f2f89c1c0c4ff16adfb2b07a7011c240f5","baseRef":"refs/heads/main","baseCommit":"97d4f5199f7f7e86cc818e5451ecb0800752d516","sourceTree":"4e4044d6876c3a2f5a24d0b161edfd25d8dd99d1","absentOptional":[]} -->

## Findings

### 10/F-04 [P2] closed - A malformed Neon URL can echo its password into the refresh log and summary

**File:** pipeline.py:277
**Found:** 2026-09-24 by /audit independent (scope: current; lens: security)
**Why it matters:** The spec says the Neon URL is never printed, logged or
written to a file, and `logs/refresh/*.log` "never contains the Neon URL".
`pipeline.py` itself never prints it, but it now streams the publish child's
output verbatim into the console, the refresh log, and (via `publish_facts`)
the summary. If the URL is entered at the hidden prompt, or set in the
environment, wrapped in quotes (for example copied from a `.env` line), the
child's `neon_connect` -> `psycopg2.connect` rejects it with
`invalid dsn: invalid connection option "..."`, and libpq echoes the URL text
up to the first `=` (scheme, user, password and host) inside that error.
`neon_publish/main.py` prints it as `Publish failed ...: <error>`, so the
password lands in the refresh log twice (stage output and summary). Reproduced
locally with a fake value through `psycopg2.extensions.parse_dsn` (the check
`psycopg2.connect` runs first): double- and single-quoted URLs echoed the
password; the bare URL parsed. Impact is limited to the owner's machine
(`logs/` is git-ignored, and the publisher's own log already had this
behaviour), so this is not a blocker, but it breaks the stated contract and the
existing "URL never in the log" test only covers the pipeline's own lines.
**Suggested fix:** In `refresh`, give the publish stage an `emit` that replaces
the URL and its password component (`urllib.parse.urlsplit(url).password`, when
present) with `***` before calling `log.line` and appending to
`facts.publish_lines`; optionally also strip one pair of surrounding quotes from
the prompt answer. Add a test whose fake publish stage emits the URL/password
and assert neither appears in the log or summary. No current requirement is
lost.
**Resolution:** fixed in `feature/manual-refresh-command` step 5: `unquote` strips one pair of surrounding quotes from the URL (environment or prompt), and every publish-stage line passes through `redactor(url)`, which replaces the URL and its password with `***` before the console, the log or the summary. Test `test_publish_output_echoing_the_url_or_password_is_redacted`. Awaiting re-review. Note: `neon_publish`'s own log (`logs/neon_publish/`) is outside this feature and keeps its pre-existing behaviour.
Re-review 2026-09-24 (independent, fresh subagent, target 66ebaa6): reopened.
The repair removes the matched-quotes case (the URL is unquoted and then
parses), but not the defect in the title. `redactor` (pipeline.py:200-219)
takes the password from `urlsplit(url).password`, which is `None` exactly when
the URL is malformed, and replacing the whole URL string does not match the
prefix that libpq echoes. Reproduced locally with a fake password through
`pipeline.unquote`, `psycopg2.extensions.parse_dsn` (the check
`psycopg2.connect` runs first) and `pipeline.redactor`: a URL with one stray
leading quote plus the usual `?sslmode=require` (for example a `.env` value
copied without its closing quote), and a URL wrapped in typographic quotes,
still leave the password in the redacted `Publish failed ...` line, which
reaches the console, the refresh log and the summary. Matched quotes, a bare
URL and Neon's `psql '...'` snippet do not leak.
Suggested repair: find the password without relying on a well-formed URL (for
example redact the text between `://` and the next `@` with a regex on the raw
value), or stop before publishing with a clear message when
`urlsplit(url)` has no `postgres`/`postgresql` scheme or no host; add a test
with a stray-quote URL whose fake publish stage echoes the libpq prefix.

Repair 2 (2026-09-24, step 5): a URL that is not `postgres[ql]://user:password@host/...` is refused before the publish stage runs (message never shows the value; publish stays pending), so a malformed URL never reaches libpq; and `redactor` also hides the raw text between `://` and `@` and its password part, whether or not the URL parses. Tests: `test_malformed_neon_url_is_refused_before_publish_and_never_shown` (stray quote, curly quotes, garbage) and `test_redactor_hides_credentials_even_when_the_url_does_not_parse`. Awaiting re-review.
Re-review 2026-09-24 (independent, fresh subagent, target ca4598f): closed.
`looks_like_postgres_url` (pipeline.py:200-208) now refuses, before the publish
stage runs and without showing the value, every case named above: one stray
leading quote with `?sslmode=require`, typographic quotes, Neon's `psql '...'`
snippet, a missing scheme and key=value strings; matched quotes are stripped by
`unquote` and then parse. Local check with a fake password through
`pipeline.resolve_neon_url`, `looks_like_postgres_url`,
`psycopg2.extensions.parse_dsn` and `pipeline.redactor` (22 variants): every
accepted URL either parses or produces a libpq parse error that the redactor
fully hides (upper-case scheme, space in the path, bad percent-encoding, `%00`,
bad query). The refusal and redaction messages never contain the URL, and the
URL still reaches the publish child only through its environment. No new leak
introduced by the repair. A separate, narrower gap (an unencoded `@` inside the
password) is recorded as F-07.

### 10/F-05 [P3] closed - A failed load reports "no rows loaded" even when earlier tables were committed

**File:** pipeline.py:159
**Found:** 2026-09-24 by /audit independent (scope: current; lens: quality)
**Why it matters:** The spec says a value missing from the stage output is
shown as "not run", never as 0. When the load fails before its `Finished:`
line, the summary prints `Load:     no rows loaded`. `postgres_etl` commits one
table at a time (`with connection:` per table in `flat_loader._load_table`), so
tables before the failing one were already replaced in local PostgreSQL; the
summary then states zero where the true count is unknown.
**Suggested fix:** When no `Finished:` line was seen, print an unknown/not
reported marker (for example `rows not reported`) instead of `no`, and extend
the load-failure summary test to assert it.
**Resolution:** fixed in step 5: an unfinished load shows "rows loaded unknown (the load did not finish)". Test `test_unfinished_load_reports_unknown_rows_not_zero`. Awaiting re-review.
Re-review 2026-09-24 (independent, fresh subagent, target 66ebaa6): closed.
`build_summary` (pipeline.py:160-161) prints "rows loaded unknown (the load did
not finish)" when no `Finished:` line was seen; a real `0` row count is still
shown because the captured value is a non-empty string. The test asserts the
unknown text and the absence of "no rows"; all three test commands pass. No new
defect introduced.

### 10/F-06 [P3] closed - README tells the owner to type the Neon URL into a PowerShell command

**File:** README.md:28
**Found:** 2026-09-24 by /audit independent (scope: current; lens: security)
**Why it matters:** The documented way to set `NEON_DATABASE_URL` is typing
`[Environment]::SetEnvironmentVariable(..., "<direct Neon URL>", "User")` in the
terminal. PSReadLine saves that line, credential included, to its plain-text
history file, where it outlives a later change or removal of the variable
(the default sensitive-history filter does not match a connection URL). The
user-level variable itself is an accepted part of the spec.
**Suggested fix:** Document setting the variable through Windows "Edit
environment variables for your account" instead, or read the value with a
masked `Read-Host` (`-MaskInput` in PowerShell 7; `-AsSecureString` in Windows
PowerShell 5.1) inside the same command so the URL is never on the command line. Docs-only change; no current requirement is lost.
**Resolution:** fixed in step 5: the README now points to the Windows "Edit environment variables for your account" dialog and warns against typing the URL into a terminal command. Awaiting re-review.
Re-review 2026-09-24 (independent, fresh subagent, target 66ebaa6): closed.
README.md "Run a refresh" now documents the "Edit environment variables for
your account" dialog and warns that PowerShell keeps a plain-text history; no
command with the URL on the command line remains in README.md or the AGENTS.md
Commands section. No new defect introduced.

## Independent review

# Independent Review

**Status:** passed
**Target commit:** ca4598f2f89c1c0c4ff16adfb2b07a7011c240f5
**Base commit:** 97d4f5199f7f7e86cc818e5451ecb0800752d516
**Base ref:** main
**Spec hash:** 9b5bff8fedaa05cbf907e97100ee557b3bdc1fc935bdadca7addc894668dae30
**Prepared by:** claude
**Builder model:** claude-opus-5-5
**Requested reviewer:** claude
**Requested model:** claude-opus-5-5
**Requested execution:** automatic
**Requested at:** 2026-09-24T20:28:06+00:00
**Workflow:** regular
**Check required:** no
**Reviewer adapter:** claude
**Reviewer model:** claude-opus-5-5
**Reviewer context:** fresh subagent
**Actual execution:** automatic
**Reviewed at:** 2026-09-24T20:31:26+00:00
**Scope:** current
**Lenses:** quality, security, performance, tests
**Verdict:** passed
**Check result:** not-required

## Handoff

Review the active spec and the complete `97d4f5199f7f7e86cc818e5451ecb0800752d516..ca4598f2f89c1c0c4ff16adfb2b07a7011c240f5` delta in a fresh
session or isolated subagent without the builder conversation. Run all Audit lenses from scratch.
Run Check when required above. Do not edit product code, accept findings, or
reuse the existing findings as the review scope.

## Commands

- `git rev-parse HEAD`, `git merge-base main HEAD`, `sha256sum blueprint/context/current-feature.md`, `git status --porcelain --untracked-files=all`: pass (target, base and spec hash match; only `blueprint/context/review.md` differed)
- `cd api_requests && python -m unittest tests.test_scrapper`: pass (16 tests)
- `python -m unittest discover -s postgres_etl/tests`: pass (38 tests)
- `python -m unittest neon_publish.tests.test_publish tables_to_csv.tests.test_csv_export`: pass (27 tests, including 15 refresh-command tests)
- `python pipeline.py --help`: pass (lists `-sc`, `--force`, `--skip-fetch`, `--dry-run-publish`, `--allow-shrink`)
- Local Python snippet with fake credentials over `pipeline.resolve_neon_url`, `looks_like_postgres_url`, `redactor` and `psycopg2.extensions.parse_dsn` (22 URL variants, no network or database): pass, except the unencoded-`@` case recorded as F-07

## Evidence

- Delta reviewed in full: `pipeline.py`, `neon_publish/tests/test_publish.py`, `.vscode/tasks.json`, `README.md`, `AGENTS.md`, `blueprint/context/current-feature.md`; callers and contracts checked in `neon_publish/main.py`, `neon_publish/publish.py` (`neon_connect`), `api_requests/main.py` (summary file), `common/db.py` (`log_directory`), `.gitignore` (`logs/`, `.env`).
- Neon URL: read from `NEON_DATABASE_URL` or a `getpass` prompt only after the load succeeds and only on an interactive stdin; unquoted, shape-checked before publishing, passed to the publish child only through its environment; never in argv, the stage header, the state file, the refusal messages or the summary. Publish-stage lines pass through `redactor` before console, log and summary.
- Spec steps 1-5 match the code: streamed stages with UTF-8 child output, one log per run under `logs/refresh/`, summary with "not run" and "unknown" markers, exit codes 0/stage/1/130/2, two VS Code tasks, README "Run a refresh" section and AGENTS.md Commands.
- F-04 re-examined against the repaired code and closed; F-07 (P3) added.

## Findings

- F-04 [P2] closed (malformed Neon URL echo; repair verified)
- F-07 [P3] open (password with an unencoded `@` passes the check; partial tail can reach the log)
- F-03 [P3] unverified (pre-existing, outside this delta; unchanged)

## Remaining risk

- No live refresh, database or Neon run was performed (by design); the real dry run through the VS Code task is the owner's check and was not required here.
- The libpq connection-time error for F-07 was reproduced from `parse_dsn` output and libpq's message format, not from a live connection attempt.
- An unexpected Python exception inside `pipeline.py` itself (not a failing stage) would end the run with a console traceback and no summary; no reachable trigger was found.
- No lint, typecheck or combined Verify command exists in this project (AGENTS.md), so none could run.
