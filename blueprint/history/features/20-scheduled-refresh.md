# Feature: Scheduled refresh

**From build-plan:** feature 20
**Build attempt:** 1
**Branch:** feature/scheduled-refresh
**Status:** verified

## Goal

Run the current-season refresh (`python pipeline.py`) automatically every day
at 06:00 on the owner's Windows laptop with Windows Task Scheduler. It needs
no manual step and leaves the same log and summary as a manual run. A daily
morning run covers "nightly and after each round": evening games are about
7.5 hours old by 06:00, and the fetcher's 48-hour hot window re-fetches any
game whose data was still incomplete.

## In scope

- One committed PowerShell script at the repository root,
  `register_refresh_task.ps1`. It creates or updates one scheduled task for
  the current Windows user, and `-Remove` deletes it. Running it again is
  safe: it replaces the task with the same definition.
- Task definition (see Data / contracts): daily at 06:00 local time, runs only
  while the owner is logged on (no stored password, no admin rights), and
  starts as soon as possible after a missed start (laptop off or asleep at
  06:00). It runs on battery and keeps running when unplugged, never starts a
  second copy, and is stopped after 2 hours.
- The task runs `pipeline.py` from the repository folder with the Python found
  when the script runs, so `.env`, `postgres_etl/config_connection.json`,
  `data/` and `logs/refresh/` resolve exactly as in a manual run.
- Unattended safety: the pipeline must see no interactive console, so a
  missing Neon URL fails cleanly ("FAILED at Publish (missing Neon URL)") and
  never waits at a hidden prompt. The task's Last Run Result is the
  pipeline's own exit code (0 = OK).
- Docs: a "Scheduled refresh" section in `README.md` (register, check
  status/last result/next run, run now, remove, where logs are), the Commands
  list in `AGENTS.md`, the Deployment passage in
  `blueprint/context/project-overview.md`, and the `pipeline.py` docstring
  line that says it is run from the VS Code terminal.
- Registering the task on the owner's laptop and checking its definition.

## Out of scope

- GitHub Actions. The pipeline needs the local Bronze cache (336 MB,
  gitignored), the local PostgreSQL warehouse with every season (records and
  identities use all loaded seasons) and `data/state`. A fresh runner has none
  of these, and the publisher's shrink guard would refuse its output.
  GitHub Actions remains the likely home for item 17's test run.
- Changes to what `pipeline.py` fetches, loads, builds or publishes, its
  flags, or its logs.
- Notifications (toast, email), a separate status file, retries within the
  same day, or a lock against a manual run overlapping the scheduled one.
  Feature 10 excluded notifications. A failed run is retried by the next
  day's run, and a pending publish is retried automatically.
- Waking the laptop from sleep for the run (off by default; see Notes).
- `--all` or any other scheduled mode, and EuroCup (feature 18).

## Build loop

- `workflow.stepReview` is `feature`: build all steps, then present one review
  packet. `workflow.checkpointCommits` is `disabled`: no step commits.
  `/complete` creates the single feature commit.
- Registering the task (step 3) and any live run happen only after the
  owner's explicit yes in the chat at that point.

## Build steps

- [x] **Step 1 - Registration script.** Write `register_refresh_task.ps1`
  using the built-in `ScheduledTasks` module (`Register-ScheduledTask`,
  `New-ScheduledTaskAction/Trigger/Settings/Principal`,
  `Unregister-ScheduledTask`):
  - The working folder is `$PSScriptRoot`.
  - Resolve Python with `Get-Command python -CommandType Application`, and
    stop with a clear message if none is found or the first match is the
    `WindowsApps` Store stub. Store that absolute path in the task.
  - The action is hidden `powershell.exe -NoProfile -WindowStyle Hidden`. It
    runs the stored Python on `pipeline.py` with standard input redirected
    away from the console, then `exit $LASTEXITCODE`.
  - `-Force` replaces an existing task.
  - `-Remove` unregisters the task without a confirmation prompt and says
    whether a task existed.
  - On success, print the task name, Python path, working folder and next run
    time.
  - The script never starts the task.

  *Done when:* PowerShell's parser reports no errors for the file. Reviewing
  the code shows every setting in Data / contracts. Running `-Remove` when no
  task exists prints "not registered" and exits 0.

- [x] **Step 2 - Docs.** Add the README "Scheduled refresh" section with the
  exact commands:
  - Register: `powershell -ExecutionPolicy Bypass -File register_refresh_task.ps1`
    (works with Windows' default execution policy).
  - Status: `Get-ScheduledTaskInfo -TaskName "JMP Warehouse refresh"` for the
    last run time, last result and next run time.
  - Run now: `Start-ScheduledTask` (a live publish).
  - Remove: the script with `-Remove`.
  - Logs: the newest file in `logs/refresh/`.

  State that a registered task is the owner's standing approval for the daily
  live E2026 publish, and that removing the task withdraws it. Update
  `AGENTS.md` Commands, the overview Deployment passage and the `pipeline.py`
  docstring line.

  *Done when:* each doc names the same task name, time and commands as the
  script, and nothing still says scheduling is a later feature.

- [x] **Step 3 - Register and verify (owner approval).** After the owner says
  yes, run the script on the laptop. Check the task read-only with
  `Get-ScheduledTask` and `Get-ScheduledTaskInfo`.

  *Done when:* the task exists for the owner's user with:
  - a daily trigger at 06:00
  - logon type Interactive and run level Limited
  - StartWhenAvailable on
  - battery start and keep-running allowed
  - MultipleInstances IgnoreNew
  - execution time limit 2 hours
  - working folder set to the repository
  - next run time the coming 06:00

  The first real run is checked in `/check`: a new `logs/refresh/` log
  stamped around 06:00 (or soon after the laptop wakes) ending in
  `Result: OK`, and Last Run Result 0. That first run publishes live. A
  manual `Start-ScheduledTask` run before then needs its own owner yes. All
  four test commands still pass.

- [x] **Step 4 - Repair review findings F-06 and F-07.**
  - F-06: the task action exits 1 when Python never ran (`$LASTEXITCODE`
    unset), so a missing Python path can no longer show as 0 (OK).
  - F-07: the README says any non-zero result is a failed run, not only `1`.
  - After the owner's yes, re-run the registration script so the task uses
    the new action.

  *Done when:* the action command line, run against a missing Python path,
  exits 1. Against a real Python, it still prints `isatty()` False and passes
  exit code 3 through. The script still parses with no errors. The
  re-registered task's action contains the new check. All four test
  commands pass.

- [x] **Step 5 - Repair review finding F-08 (daylight saving).**
  `New-ScheduledTaskTrigger` stores the start boundary with the current UTC
  offset (`+02:00`). That turns on "Synchronize across time zones", so after
  daylight saving ends the run would happen at 05:00 local. Set the
  trigger's start boundary to local 06:00 with no offset, then re-register
  after the owner's yes.

  *Done when:* the script parses with no errors, and `Export-ScheduledTask`
  shows a `StartBoundary` with no offset (`...T06:00:00`). The next run time
  is still 06:00, all other settings and the action are unchanged, and all
  four test commands pass. The actual 06:00 run after the daylight saving
  change (2026-10-25) is observed in `/check`.

- [x] **Step 6 - Repair review findings F-09 and F-10.**
  - F-09: format the start boundary with the culture-invariant `"s"` format,
    so a non-colon time separator cannot break registration.
  - F-10: start at the next 06:00, which is tomorrow when registering after
    06:00. A past start can then never count as a missed start and publish
    at once.
  - After the owner's yes, re-register.

  *Done when:* the script parses with no errors. A probe of the same
  expressions gives `...T06:00:00` under `fi-FI` and `en-GB`, and today's
  date before 06:00 but tomorrow's after. The re-registered task's
  `StartBoundary` has no offset, the next run is still 06:00, all other
  settings and the action are unchanged, and all four test commands pass.

## Files / areas

- New: `register_refresh_task.ps1` (repository root, next to `pipeline.py`)
- Edited: `README.md`, `AGENTS.md`, `blueprint/context/project-overview.md`,
  `blueprint/project-plan.md` (Deployment, approved by the owner),
  `pipeline.py` (docstring only)
- Unchanged and relied on: `pipeline.py` behavior: `.env` lookup via
  `resolve_neon_url`, the non-interactive branch keyed on `sys.stdin.isatty()`,
  exit codes, and `logs/refresh/` logs

## Data / contracts

Scheduled task contract (the only new persisted object, stored in Windows Task
Scheduler, not in the repo):

| Setting | Value |
| --- | --- |
| Task name / path | `JMP Warehouse refresh` in the root folder `\` |
| Trigger | Daily, 06:00 local time; start boundary is the next 06:00, stored without a time-zone offset (culture-invariant `s` format) so it follows daylight saving |
| Principal | Current user, logon type Interactive (runs only while logged on), run level Limited, no stored password |
| Action | `powershell.exe -NoProfile -WindowStyle Hidden -Command "<stdin redirected> & '<python.exe>' pipeline.py; exit $LASTEXITCODE"` |
| Working directory | Repository root (`$PSScriptRoot`) |
| StartWhenAvailable | On (catch up after a missed 06:00) |
| AllowStartIfOnBatteries / DontStopIfGoingOnBatteries | On / On |
| WakeToRun | Off |
| MultipleInstances | IgnoreNew |
| ExecutionTimeLimit | 2 hours (a normal run takes about 10 minutes) |

Last Run Result is `pipeline.py`'s exit code: 0 OK, any other value a failed
run (usually 1; a failed stage passes on its own code). If Python could not be
started (stored path gone), the action exits 1, never 0. 0x41301 means the
task is running, and 0x41306 means Task Scheduler stopped it at the time limit.

## Testing

- No Python logic changes, so no new unit tests. Regression check: the four
  test commands in `AGENTS.md` pass (the `neon_publish` suite also covers
  `pipeline.py`).
- No Verify command exists yet (item 17), so it is not run.
- The script is checked by a PowerShell parse check and the `-Remove`
  no-task path (step 1), and by read-only `Get-ScheduledTask` inspection after
  registration (step 3). Live evidence is the first scheduled run's log and
  Last Run Result, recorded in `/check`, never claimed beforehand.

## Notes for the AI

- Standard input must not be a console. On Windows, `NUL` can still report
  `isatty()` as True, so feed an empty pipe rather than `< NUL`. Confirm the
  chosen form by running the same command line by hand with a one-line Python
  probe (`python -c "import sys; print(sys.stdin.isatty())"` → `False`). Do
  not probe with `pipeline.py`.
- `-WindowStyle Hidden` still shows a PowerShell window for a split second at
  start. That is expected. Do not add a VBScript or other launcher to hide it.
- Do not use `schtasks.exe`: it cannot set the working directory,
  StartWhenAvailable or the battery settings.
- Never run `Start-ScheduledTask` or `pipeline.py` without a live owner yes:
  both publish to Neon.
- Use PowerShell 5.1-compatible syntax (no `&&`, `??` or ternaries).
- If the owner later wants the laptop woken from sleep, it is one setting
  (`-WakeToRun`) and needs the laptop plugged in. Leave it off unless asked.
- Never print or log the Neon URL. The script does not read `.env`.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":11706,"specSha256":"9e713d810d2c9012fa9beb93fccd483ccfd5ae8142c3abc7f0353d0dcd80eb16","branch":"refs/heads/feature/scheduled-refresh","head":"da2ae8cf7d9de467ef790d9d8221bdb692439043","baseRef":"refs/heads/main","baseCommit":"217fe6e95758b5fb704e126fbd9a54e8d8084445","sourceTree":"1b6647eea59db1ee4c3a28527de7a43dbe8c88a6","absentOptional":[]} -->

## Findings

### 20/F-06 [P2] closed - Scheduled task reports 0 (OK) when the stored Python no longer exists

**File:** register_refresh_task.ps1:45
**Found:** 2026-10-23 by /audit independent (scope: current; lenses: quality, security, performance, tests)
**Why it matters:** the task action is
`@() | & '<python.exe>' pipeline.py; exit $LASTEXITCODE`. If the stored Python
path is gone (Python upgraded to a new folder or uninstalled, which the README
expects with "update it after Python ... moves"), `&` raises a
statement-terminating CommandNotFoundException, `$LASTEXITCODE` is never set,
and `exit $null` exits 0. Reproduced read-only:
`powershell.exe -NoProfile -Command "@() | & 'C:\no\such\dir\python.exe' pipeline.py; exit $LASTEXITCODE"`
exits 0. Last Run Result would then show 0 (documented as OK) every day while
nothing runs and no log is written. That breaks the spec contract "The task's
Last Run Result is the pipeline's own exit code (0 = OK)", and Last Run Result
is the only health signal because notifications are out of scope.
**Suggested fix:** make a launch failure exit non-zero, for example build the
command as `"@() | & '{0}' pipeline.py; if (`$null -eq `$LASTEXITCODE) {{ exit 1 }}; exit `$LASTEXITCODE"`
(the braces are doubled for `-f`), then re-register after owner approval. No
current requirement would be lost.
**Resolution:** fixed 2026-10-24 in feature 20 step 4. The action now runs
`if ($null -eq $LASTEXITCODE) { exit 1 }` before `exit $LASTEXITCODE`. A
missing Python path now exits 1 (probe), and real Python still passes exit 3
through. The task was re-registered with the new action.
Closed 2026-10-23 by /audit independent (fresh subagent) against 4445749:
register_refresh_task.ps1:45 builds the guarded command. The exact action string
with a stand-in script exits 1 for a missing Python path, 3 and 130 pass through,
and a missing script exits 2. The registered task's Arguments contain the guard.
No new defect found in the repair.

### 20/F-07 [P3] closed - Docs say exit code 1 means a failed stage, but a stage failure returns the child's own code

**File:** README.md:195
**Found:** 2026-10-23 by /audit independent (scope: current; lenses: quality, security, performance, tests)
**Why it matters:** `pipeline.refresh` returns the failing child stage's exit
code as-is (`pipeline.py:370`, `:395`, `:404`, `:410`, `:430`), and `main`
returns 130 on Ctrl+C. The README ("`1` means a stage failed") and the spec's
"0 OK, 1 failed stage, 2 bad arguments" therefore miss cases. For example, a
child argparse error returns 2, which the spec labels "bad arguments", although
the scheduled run passes no arguments. This is low impact because most child
failures exit 1.
**Suggested fix:** reword the README to say "a non-zero result means a stage
failed (see the newest log); `0x41301` ... `0x41306` ...". No behavior change.
No current requirement would be lost.
**Resolution:** fixed 2026-10-24 in feature 20 step 4. The README now says 0 is
OK and any other number is a failed run (usually 1), with a hint to check the
registered Python when no new log was written. The spec's exit-code note was
updated to match.
Closed 2026-10-23 by /audit independent (fresh subagent) against 4445749:
README.md:195 now says 0 is OK and any other number is a failed run (usually 1).
The spec's Data / contracts note says the same. Both match `pipeline.refresh` and
`main`, which return a child's own code, 1, 2 or 130.

### 20/F-08 [P3] closed - Daily trigger is pinned to UTC+2, so it may run at 05:00 after daylight saving ends

**File:** register_refresh_task.ps1:49
**Found:** 2026-10-23 by /audit independent (scope: current; lenses: quality, security, performance, tests)
**Why it matters:** `New-ScheduledTaskTrigger -Daily -At "06:00"` stored
`<StartBoundary>2026-10-24T06:00:00+02:00</StartBoundary>` (read-only
`Export-ScheduledTask`). A StartBoundary with an offset is Task Scheduler's
"Synchronize across time zones" mode. In that mode the start time is commonly
kept as a fixed UTC instant. The machine's zone (Central Europe Standard Time)
leaves daylight saving time on 2026-10-25. If the time stays fixed in UTC, the
task runs at 05:00 local from then until the end of March, not at the 06:00
local time the spec's contract and the docs state. The run would still work and
publish. Only the time would differ, so the impact is small. Not confirmed: it
can't be shown without waiting for the change or registering a test task, and
this review was not allowed to register one.
**Suggested fix:** validate first. After the 2026-10-25 run, read
`Get-ScheduledTaskInfo -TaskName "JMP Warehouse refresh"`. If NextRunTime shows
05:00 (or that run's log is stamped around 05:00), give the trigger a local start
boundary with no offset before registering, for example
`$trigger.StartBoundary = (Get-Date "06:00").ToString("yyyy-MM-ddTHH:mm:ss")`,
then re-register after owner approval. No current requirement would be lost.
**Resolution:** fixed 2026-10-24 in feature 20 step 5, before the change was
observed. The owner chose to repair it ahead of the daylight saving change. The
script now sets `$trigger.StartBoundary` to local 06:00 with no offset. After
re-registration, `Export-ScheduledTask` shows
`<StartBoundary>2026-10-24T06:00:00</StartBoundary>` and NextRunTime 06:00.
The first run after 2026-10-25 is to be confirmed in `/check`.
Re-examined 2026-10-24 by /audit independent (fresh subagent) against 7992728,
not closed: register_refresh_task.ps1:52 removes the offset, and read-only
`Export-ScheduledTask` shows `StartBoundary 2026-10-24T06:00:00` with NextRunTime
06:00, so the original defect is gone on this machine. The repair line itself
introduced F-09 (culture-dependent `:` in the format string), so per the closing
rule this stays `fixed` until F-09 is repaired and re-reviewed. P3, not blocking.
F-09 was repaired in step 6 on 2026-10-24 (culture-invariant `"s"` format).
F-08 is ready for re-review.
Closed 2026-10-24 by /audit independent (fresh subagent) against da2ae8c:
register_refresh_task.ps1:56 sets `$trigger.StartBoundary = $start.ToString("s")`,
which has no offset, and F-09 (introduced by the earlier repair line) is closed
in this pass. Read-only `Export-ScheduledTask` shows
`<StartBoundary>2026-10-24T06:00:00</StartBoundary>`, a daily trigger with
DaysInterval 1, and NextRunTime 06:00. No new defect found in the repair. The
live 06:00 run after the 2026-10-25 daylight saving change is still to be
observed in `/check`.

### 20/F-09 [P3] closed - StartBoundary format uses the culture's time separator

**File:** register_refresh_task.ps1:52
**Found:** 2026-10-24 by /audit independent (scope: current; lenses: quality, security, performance, tests)
**Why it matters:** in a .NET custom format string `:` is the current culture's
time separator, not a literal colon. `(Get-Date "06:00").ToString("yyyy-MM-dd'T'HH:mm:ss")`
yields `2026-10-24T06.00.00` under `fi-FI` (probe with an explicit culture), and
the same happens when a user customizes the Windows time separator. Task
Scheduler rejects that StartBoundary, so registration fails (loudly, under
`$ErrorActionPreference = "Stop"`). The owner's current culture is `en-GB` with
`:`, so today's registration works; the risk is a later Region-setting change.
**Suggested fix:** use the culture-invariant sortable format,
`(Get-Date "06:00").ToString("s")`, which gives `2026-10-24T06:00:00` with no
offset in every culture. No current requirement would be lost.
**Resolution:** fixed 2026-10-24 in feature 20 step 6. The start boundary now
uses `.ToString("s")`. A probe of the same expression gives
`2026-10-24T06:00:00` under both `fi-FI` and `en-GB`, where the old format gave
`06.00.00` under `fi-FI`. The task was re-registered.
Closed 2026-10-24 by /audit independent (fresh subagent) against da2ae8c:
register_refresh_task.ps1:56 uses `.ToString("s")`. A probe of `Get-Date "06:00"`
plus `"s"` under fi-FI, en-GB, en-US, de-DE, ar-SA (UmAlQura), th-TH (Thai
Buddhist) and fa-IR (Persian) gives `2026-10-24T06:00:00` every time, with a
colon separator and a Gregorian date. No new defect found in the repair.

### 20/F-10 [P3] closed - Re-registering after 06:00 may start the task at once

**File:** register_refresh_task.ps1:52
**Found:** 2026-10-24 by /audit independent (scope: current; lenses: quality, security, performance, tests)
**Why it matters:** the trigger's StartBoundary is always today at 06:00, and
StartWhenAvailable is on. When the script is run again after 06:00 (the README
says to re-register after Python or the folder moves), `-Force` replaces the task
with a start boundary already in the past. Task Scheduler may treat today's 06:00
as a missed start and launch the task right away, a live Neon publish, although
the script and spec say registering never starts the task. Not confirmed: every
registration so far happened before 06:00 (StartBoundary dated 2026-10-24,
registered after midnight), the TaskScheduler Operational log is disabled, and
this review may not register a test task.
**Suggested fix:** validate first by checking LastRunTime/the newest
`logs/refresh/` file right after a later-than-06:00 re-registration that the
owner approves anyway. If it fires, start the boundary at the next 06:00, for
example `$start = Get-Date "06:00"; if ($start -le (Get-Date)) { $start = $start.AddDays(1) }`.
No current requirement would be lost.
**Resolution:** fixed 2026-10-24 in feature 20 step 6. The owner chose to apply
the suggested fix without waiting to confirm the behavior. The start boundary
is now the next 06:00, using the suggested lines. A probe of the same logic
gives today 06:00 for 01:45 and tomorrow 06:00 for 14:00, in both cultures. A
past start boundary therefore can no longer be written. Re-registered at 01:4x:
StartBoundary `2026-10-24T06:00:00`, NextRunTime 06:00, LastRunTime unchanged
(01:16:42).
Closed 2026-10-24 by /audit independent (fresh subagent) against da2ae8c:
register_refresh_task.ps1:54-56 starts at today's 06:00 and moves it to tomorrow
when that time is not in the future (`-le`). Probe of the same logic at fixed
clocks: 01:45, 05:59:59 and 02:30 on the DST day give that day's 06:00, while
06:00:00, 14:00 and 23:59:59 give the next day's 06:00, so a past start boundary
can no longer be written. At review time (01:51 local) the registered task shows
StartBoundary `2026-10-24T06:00:00`, NextRunTime 06:00 and LastRunTime still
01:16:42. No new defect found in the repair.

## Independent review

**Status:** passed
**Target commit:** da2ae8cf7d9de467ef790d9d8221bdb692439043
**Base commit:** 217fe6e95758b5fb704e126fbd9a54e8d8084445
**Base ref:** refs/heads/main
**Spec hash:** 9e713d810d2c9012fa9beb93fccd483ccfd5ae8142c3abc7f0353d0dcd80eb16
**Prepared by:** claude
**Builder model:** claude-opus-5-5
**Requested reviewer:** claude
**Requested model:** claude-opus-5-5
**Requested execution:** automatic
**Requested at:** 2026-10-23T23:48:39Z
**Workflow:** regular
**Check required:** no
**Reviewer adapter:** claude
**Reviewer model:** claude-opus-5-5
**Reviewer context:** fresh subagent
**Actual execution:** automatic
**Reviewed at:** 2026-10-23T23:53:00Z
**Scope:** current
**Lenses:** quality, security, performance, tests
**Verdict:** passed
**Check result:** not-required

### Handoff

Review the active spec and the complete `217fe6e95758b5fb704e126fbd9a54e8d8084445..da2ae8cf7d9de467ef790d9d8221bdb692439043` delta in a fresh
session or isolated subagent without the builder conversation. Run all Audit lenses from scratch.
Run Check when required above. Do not edit product code, accept findings, or
reuse the existing findings as the review scope.

### Commands

- `git rev-parse HEAD`, `git merge-base refs/heads/main HEAD`, `sha256sum blueprint/context/current-feature.md`, `git status --porcelain --untracked-files=all`: pass (target, base and spec hash match; only review.md and findings.md differ)
- `git diff 217fe6e..da2ae8c` (7 files: register_refresh_task.ps1, pipeline.py docstring, README.md, AGENTS.md, project-overview.md, project-plan.md, current-feature.md): reviewed
- `[System.Management.Automation.Language.Parser]::ParseFile(register_refresh_task.ps1)`: pass (0 errors)
- Exact task action string (built with the script's own expression), run in a new hidden console against a stand-in `pipeline.py` in the scratchpad: pass (stdin.isatty False, control without the empty pipe True; exit 0, 1, 3, 130 pass through; missing Python path exits 1)
- Culture probe of `Get-Date "06:00"` plus `.ToString("s")` under fi-FI, en-GB, en-US, de-DE, ar-SA, th-TH, fa-IR: pass (`2026-10-24T06:00:00` every time)
- Next-06:00 logic at fixed clocks (01:45, 05:59:59, 06:00:00, 14:00, 23:59:59, 02:30 on the DST day): pass
- Not-registered branch of `-Remove` (same lookup under `$ErrorActionPreference = "Stop"` against a nonexistent task name): pass ("not registered", exit 0)
- `Get-ScheduledTask` / `Get-ScheduledTaskInfo` / `Export-ScheduledTask` for `JMP Warehouse refresh` (read-only): pass (matches the target script and the Data / contracts table)
- `cd api_requests && python -m unittest tests.test_scrapper`: pass (46 tests)
- `python -m unittest discover -s postgres_etl/tests`: pass (214 tests)
- `python -m unittest discover -s gold_etl/tests`: pass (283 tests)
- `python -m unittest neon_publish.tests.test_publish tables_to_csv.tests.test_csv_export`: pass (72 tests)
- Combined Verify command: unavailable (none exists yet, build-plan item 17)
- Live scheduled run (`Start-ScheduledTask` / 06:00 trigger) and `register_refresh_task.ps1` / `-Remove` on the real task: unavailable (not permitted in review; external side effects)

### Evidence

- Registered task: principal Korisnik / Interactive / Limited; action `powershell.exe -NoProfile -WindowStyle Hidden -Command "@() | & '<Python313\python.exe>' pipeline.py; if ($null -eq $LASTEXITCODE) { exit 1 }; exit $LASTEXITCODE"`, working directory D:\jmp-project\jmp-warehouse; daily trigger with DaysInterval 1 and StartBoundary `2026-10-24T06:00:00` (no offset); StartWhenAvailable True, DisallowStartIfOnBatteries False, StopIfGoingOnBatteries False, WakeToRun False, MultipleInstances IgnoreNew, ExecutionTimeLimit PT2H; NextRunTime 2026-10-24 06:00 at review time 01:51 local.
- register_refresh_task.ps1:46 escapes `'` in the Python path for the single-quoted command, and the path is a `-f` argument, so braces in it are harmless. Lines 54-56 compute the next 06:00 with no offset. `-Remove` never prompts. The script never starts the task and does not read `.env`.
- pipeline.py:343 keys interactivity on `sys.stdin.isatty()`. pipeline.py:219 and :416 return `(1, "FAILED at Publish (missing Neon URL)")` without prompting when it is False. The only other prompt source is `getpass` at :339, and no child stage reads stdin.
- Newest refresh log `logs/refresh/refresh_20261024_011643.log` (the task's 01:16:42 run) ends with a normal summary, `Result: NOTHING TO DO`, and LastTaskResult 0.
- The docs (README Scheduled Refresh, AGENTS.md Commands, project-overview Deployment, project-plan Deployment, pipeline.py docstring) name the same task name, 06:00 time, commands and exit-code meaning as the script. Nothing still says scheduling is a later feature.
- Re-examined fixed findings F-08, F-09 and F-10 against the target and closed them with evidence in the ledger.

### Findings

- F-08 [P3] closed (re-examined against da2ae8c)
- F-09 [P3] closed (re-examined against da2ae8c)
- F-10 [P3] closed (re-examined against da2ae8c)
- F-11 [P3] open - the unattended missing-URL branch the scheduled run relies on (pipeline.py:219) has no unit test; non-blocking

### Remaining risk

- Combined Verify command unavailable (none defined yet, build-plan item 17).
- No live scheduled run was observed in this review. The first 06:00 run, its log ending `Result: OK` and Last Run Result 0, and the first run after the 2026-10-25 daylight saving change at 06:00 local are left to `/check`.
- `register_refresh_task.ps1` (register and `-Remove` on the real task) was not run in review. Its behavior was checked by parser, isolated probes of the same expressions and read-only inspection of the registered task.
- Unverified: when Task Scheduler stops the task at the 2-hour limit, it may end only `powershell.exe` and leave the `python.exe` child running. This is low impact, because a normal run takes about 10 minutes and publishing rolls back on failure.
- F-11 (P3): the non-interactive missing-URL guard is correct today but has no regression test.
