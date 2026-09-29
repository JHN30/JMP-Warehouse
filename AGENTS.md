# AGENTS.md

Instructions for AI coding agents working in this project. This is the cross-tool
entry point: Codex, OpenCode, Cursor, GitHub Copilot, Gemini CLI, Aider, Zed,
Windsurf, and others read `AGENTS.md`. Claude Code reads `CLAUDE.md`, which imports
this file, so there is a single source of truth.

Claude Code, Codex, and every other AI tool must not add AI attribution to
commits or pull requests, including AI `Co-Authored-By` trailers or generated-by
signatures. Preserve genuine human attribution. See
[Commit and PR attribution](blueprint/context/ai-interaction.md#commit-and-pr-attribution)
for optional tool settings.

## What this is

The data pipeline behind the JMP EuroLeague web app (`jmpeuroleague.com`, repo
`jmp-euroleague2`). It downloads EuroLeague API data into a bronze store of exact
responses, loads it into 28 typed tables in the local PostgreSQL `silver`
schema with quality checks, plus derived per-game advanced tables (box-score estimates and counted possessions). Gold builds 16 local source tables from Silver,
postseason player statistics, a page-shaped standings table, team-season totals,
season/game coverage, all-time records, postseason series, and cross-season
player and club identities. The 30f Gold-to-Neon cutover and first E2026
publish completed on 2026-09-28 with owner approval. Further live publishing
still requires explicit owner approval.
Python 3.13 + PostgreSQL, no web framework.
See `README.md` for the layout and
`docs/DATA_DICTIONARY.md` for the tables.

This project is built with the **AI Blueprint**, a workflow layer, not an
app skeleton. To start a new project, scaffold the app first in an empty folder
(create-next-app, Vite, etc.), then overlay these files on top. Never run a
framework scaffolder inside a directory that already holds the blueprint files
(`AGENTS.md`, `CLAUDE.md`, `.agents/`, `.claude/`, `blueprint/`); it fails
because the directory isn't empty.

The workflow is defined by the local skills and context files below.

## Proportional engineering

Build for established requirements, not hypothetical scale, threats, or future
flexibility. Reuse existing code, the standard library, native platform features,
and installed dependencies before adding machinery.

- Unknown scale or extensibility defaults to the smaller reversible design. Do
  not infer enterprise, multi-tenant, hostile-user, or compliance requirements.
- Derive trust and data-integrity boundaries from actual reachability: untrusted
  input, auth/session/ownership, shared persisted data, destructive operations,
  payments, secrets, and sensitive data.
- Ask only when an unknown materially changes behavior, architecture, persisted
  data, interoperability, a real security boundary, or cost. Otherwise choose the
  simplest repository-native implementation.
- Add an abstraction, dependency, service, configuration surface, compatibility
  layer, or security mechanism only for a current requirement.
- Simplicity never removes real trust-boundary validation, data-loss prevention,
  accessibility, explicit security requirements, configured tests, or project rules.
- Stack-specific template standards apply only when the project uses that stack.

## Read these when relevant

- `blueprint/config.json` - deterministic project workflow settings
- `blueprint/context/project-overview.md` - the project's source of truth
- `blueprint/context/coding-standards.md` - read before changing code
- `blueprint/context/ai-interaction.md` - read when running the Blueprint workflow
- `blueprint/context/current-feature.md` - the one feature, fix, or rollback being built right now

Reuse relevant context already loaded in the session. Claude Code imports only
this file; its Blueprint skills load the other files on demand.

## Project configuration

`blueprint/config.json` is the user-owned, machine-readable workflow policy for
this project. Workflow skills read the relevant settings before acting. A
missing file means built-in defaults. An invalid file falls back to defaults for
read-only status reporting, but mutating workflow commands stop and point to
`/doctor` instead of guessing.

Configuration can make review or verification stricter and can tune local
branch names and automated-mode limits. It never grants permission to commit,
merge, push, deploy, publish, send, delete data, waive a failing check, or accept
a finding. Those approval and safety boundaries are not configurable.

`qualityGates.regular` controls automatic audit, independent-review, check, and
try-guide behavior for the normal workflow and Autopilot.
`qualityGates.continuous` controls the same per-feature gates for Continuous
Mode. The existing `tryGuide` keys select `/check guide`, which generates
instructions without performing verification or recording acceptance.
Independent review defaults to `when-sensitive` in both workflows, while
audit, check, and try guide default to `manual`. Sensitive or unusually broad
work therefore selects independent review automatically; ordinary small work
does not. Setting a workflow's independent review to `manual` disables that
automatic selection, while an explicit `/audit independent current` remains
available. The other conditional modes are `when-sensitive` for audit,
`when-behavioral` for check, and `when-user-facing` for try guides. `always`
runs the gate for every work item in that workflow.

`review.independentExecution` controls how a selected independent-review gate
runs. Its default, `automatic`, uses a fresh isolated reviewer child when the
active adapter can prove isolation, exact reviewer identity and model, and
completion. Otherwise it preserves the request and falls back to the manual
handoff. This setting changes execution only; the quality-gate policy still
decides whether review is selected.
The automatic path spawns a generic child through the current runtime and gives
it the installed project-local Audit skill and review contract. It never requires
or discovers global agent roles, skills, prompts, or TraversyFlow components.
New review requests record requested execution and completed receipts record
actual execution. Manual uses `fresh session`; automatic uses `fresh subagent`;
an explicit automatic fallback records actual manual with `fresh session`.

New projects default to one review packet after all small implementation steps
(`workflow.stepReview: "feature"`) with step checkpoint commits disabled. This
keeps the normal loop reviewable without repeating the full session context after
every step. Set `stepReview` to `every` when teaching, pairing closely, or working
on a high-risk change. That restores the per-step approval pauses. To fully
restore the previous workflow, including optional checkpoint prompts after an
approved step, also set `checkpointCommits` to `enabled`. Onboarding presents
these pairs as Efficient and Guided choices, but stores only the two low-level
settings. They can be changed at any time. Both styles end with an optional
read-only code walkthrough. Review cadence controls approval pauses, not whether
the user can ask for an explanation of the finished implementation.

## Workflow

Build one feature, fix, or rollback at a time, behind review gates. Each step's instructions
are plain markdown skills any capable agent can read and follow. The workflow is
exposed through tool-specific adapters:

- Codex: `.agents/skills/<skill>/SKILL.md`
- Claude Code: `.claude/skills/<skill>/SKILL.md`
- GitHub Copilot: `AGENTS.md` plus `.agents/skills/<skill>/SKILL.md`
- OpenCode: `AGENTS.md` plus the compatible `.agents/skills/` or
  `.claude/skills/` tree already installed for the selected tools

Unused adapters can be removed. Codex, GitHub Copilot, and OpenCode can share
`.agents/`. OpenCode can also reuse `.claude/` when Claude Code is selected.
Codex-only, Copilot-only, or OpenCode-only projects can delete `CLAUDE.md` and
`.claude/`. Claude Code-only projects can delete `.agents/`, but should keep
`AGENTS.md` because `CLAUDE.md` imports it. Do not duplicate the same Blueprint
skills under `.opencode/skills/`; OpenCode already discovers the compatible
trees.

When changing shared workflow behavior, update the matching skill in both
adapter folders so Codex, Claude Code, GitHub Copilot, and OpenCode stay aligned.

Learn the feature loop: `/feature` -> `/implement` -> `/check` -> `/audit current` ->
`/complete`. Approve the Feature spec before Implement. Check proves behavior;
Audit reviews code and records findings. Showing both in this path does not
change configured gates or make Audit mandatory. `/check guide` only generates
manual instructions and never performs verification or records acceptance.

Core skills:

### Build

- `feature` - turn a build-plan item into a spec, or propose a reviewed plan addition for a genuinely new feature
- `implement` - build the current spec one small, reviewed step at a time
- `check` - prove the current spec against the running app, or use `check guide`
  for a read-only manual review guide: where to go, what to click, what to expect
- `complete` - run the final safety pass, log features, fixes, or rollbacks under `blueprint/history/`, then merge with approval

### Understand and review

- `explore` - investigate an idea against the actual code without writing files or requiring plans
- `brief` - read-only briefing on an upcoming build-plan feature (scope, dependencies, size) before you spec it
- `status` - read-only progress summary, workflow drift warning, and suggested next action
- `debug` - reproduce and isolate a failure without editing code, then hand the evidence to `fix` or `implement`
- `audit` - branch-aware or full-project review across all concerns or a focused quality, security, performance, or tests lens; `audit independent current` prepares an immutable checkpoint for a fresh reviewer session or configured isolated reviewer child; records findings in `blueprint/context/findings.md` and independent receipts in `blueprint/context/review.md`, where blocking findings or stale review state stop `complete`
- `doctor` - Blueprint health check for setup, adapters, plans, overview freshness, dashboard state, and workflow drift; it may offer to reset only malformed generated dashboard state after approval

### Plan and set up

- `onboard` - tune commands, standards, visibility, ignore rules, and tool adapters after overlaying the Blueprint onto a freshly scaffolded or early project
- `adopt` - bootstrap the Blueprint into an existing brownfield app with shipped features
- `discovery` - optional deep, multi-turn planning conversation that drafts the two user-owned plans only after review and approval; direct plan writing remains fully supported
- `overview` - distill the two planning docs into
  `blueprint/context/project-overview.md`, then offer a reviewed initial planning
  baseline commit before Feature 1
- `prototype` - optional, pre-build static mockups to lock the look
- `tests` - set up unit testing by default, or a repeatable browser harness with `tests browser`
- `ci` - explicitly set up one project-specific Verify command and matching automatic GitHub checks, with an optional local pre-push hook

### Recover and release

- `fix` - document an ad-hoc bug or change into `blueprint/context/current-feature.md`
- `rollback` - plan a safe reversal of a completed feature from its archive and exact git commit, with later-dependency review before code changes
- `release` - optional Render or Vercel deployment readiness, local config, env review, and smoke-test planning

In Codex, invoke these as skills (`$onboard`, `$discovery`, `$overview`, `$feature`,
`$implement`, and so on) or ask naturally, such as "run the overview." In Claude
Code, use the slash commands (`/onboard`, `/discovery`, `/overview`, `/feature`,
and so on). These are AI chat commands, not terminal commands. In OpenCode or
other tools without a dedicated invocation syntax, ask the agent to run the matching skill or follow its `SKILL.md` manually. The
conventions in `blueprint/context/` apply however a step is invoked. `/discovery`
is never required: users may write detailed plans directly or develop them
through any conversation before running `/overview`.

### Automation

Optional explicit-only skill: `autopilot` combines `feature` or `fix` with
`implement` in one bounded pass when directly invoked, including the configured
regular quality gates. The normal workflow stops for human approval of the spec
before implementation; Autopilot continues through that review point. It may
create checkpoint commits on the feature or fix branch after passing steps and
repair confirmed P0/P1 findings when its audit gate runs. It stops before
`/complete`, merge, push, deploy, or destructive actions.

Optional explicit-only skill: `continuous` can resume or select the next planned
feature and repeat the complete local feature lifecycle through the configured
limit or end of the build plan. It creates one branch and one local main commit
per feature, applies the Continuous quality gates, archives and merges serially,
and stops on decisions or failed safety gates. It never pushes, deploys,
publishes, sends, or performs destructive actions.

Deployment is also explicit. `/release` can prepare local Render or Vercel config
and run readiness checks, but it must stop before deploy, remote service changes,
push, or publish unless the user gives a separate yes in the current chat.

## Dashboard activity

The dashboard can show the active or most recent substantial Blueprint command
from `blueprint/.state/run.json`. This file is generated local state, ignored by
Git, and never part of a feature commit.

Commands with meaningful progress or a durable handoff should write it when the
state directory exists: `onboard`, `adopt`, `discovery`, `overview`, `feature`,
`fix`, `rollback`, `implement`, `debug`, `check`, `audit`, `tests`,
`ci`, `prototype`, `autopilot`, `continuous`, `complete`, and
`release`. Short orientation commands such as `explore`, `brief`, `status`, and `doctor`
do not write activity state. The `check guide` mode also never writes activity
state; select the Check mode before any activity call. Doctor's optional
approved reset removes malformed activity instead of recording another run.

Writing the initial activity record is the first action of a tracked command,
before project inspection, preflight, or other tool calls. This one generated
state write does not authorize product changes or bypass any safety check.

Never create or edit `run.json` directly. From the project root, use the first
helper that exists:

```text
node .agents/skills/doctor/scripts/run-state.mjs <action> <options>
node .claude/skills/doctor/scripts/run-state.mjs <action> <options>
```

Start with `start --command <skill> --summary <truthful-summary> --boundary
<boundary>`. Use `update` at meaningful milestones or for a blocker, with
`--status blocked` and `--resume <exact-command>` when recovery is needed. End
with `finish --status ready|completed --summary <truthful-summary>`. The helper
validates every field before atomically replacing the generated file. If it is
missing or fails, report the activity warning and continue the workflow without
writing a manual fallback.

The helper writes this schema:

```json
{
  "schemaVersion": 1,
  "command": "continuous",
  "status": "running",
  "summary": "Completing the remaining build plan",
  "detail": "Implementing feature 3.",
  "boundary": "local-only",
  "startedAt": "<ISO-8601 timestamp>",
  "updatedAt": "<ISO-8601 timestamp>",
  "resumeCommand": "/continuous resume",
  "progress": { "current": 2, "total": 5, "label": "features" },
  "feature": { "id": "3", "title": "Export reports" }
}
```

`status` must be `running`, `blocked`, `ready`, or `completed`. Use `ready` when
the command reached its intended review handoff, such as Autopilot waiting for
review before `/complete`. Use `blocked` with the exact recovery command when
work can resume. `boundary` must be `read-only`, `reviewed`, or `local-only`.
The progress, feature, detail, boundary, and resume fields are optional. Never
put secrets, raw logs, prompts, or user content in this file. Activity tracking
must not change a command's approval boundaries or turn a reporting failure into
a workflow failure.

## Automatic verification

Automatic GitHub checks are a separate explicit setup. `/onboard` and `/adopt`
only report existing checks and point to `/ci` or `$ci` when none exist. Running
`/ci` inspects the real project and defines one `Verify` command from checks that
already exist. Use this order when available: typecheck, tests, then build. Never
invent a test runner or another check just to fill the command.

For JavaScript and TypeScript projects, prefer a package script such as `verify`
and use the detected package manager. For other stacks, use the native task
runner or exact combined command. Record the exact command under Commands below.

The optional `.github/workflows/verify.yml` must run that same command for pull
requests and pushes to the default branch. Preserve existing workflows, use the
project's real runtime and install command, and grant only `contents: read` by
default. This setup does not add coverage, browser tests, security scans, or
version matrices; those remain later project choices. A local pre-push hook that
runs the same `Verify` command is offered as an opt-in at the end of `/ci`, and
`git push --no-verify` still bypasses it, so the remote ruleset stays the lock.

GitHub branch protection or a ruleset can require the check after the repository
is pushed, but that is a separate remote setting. Missing automatic GitHub
checks do not make the Blueprint unusable.

## Commands

Run from the repository root (the owner uses the VS Code terminal). Local
PostgreSQL settings come from `postgres_etl/config_connection.json` (not
committed; copy the `.example`). Publishing reads the direct non-pooled
`NEON_DATABASE_URL` from the environment or `.env` only after Gold quality passes.

- Refresh the current season (fetch, load, quality checks): `python pipeline.py`
  (VS Code task "Refresh current season"). Ends with a summary; each run is logged
  to `logs/refresh/refresh_<YYYYMMDD_HHMMSS>.log`.
- `python pipeline.py --dry-run-publish` builds Gold and checks Neon without
  remote writes; pending state remains true for a later live retry.
- Fetch into bronze: `python api_requests/main.py -sc <seasons>` (for example `-sc 2000-2025`)
- Load into local PostgreSQL: `python postgres_etl/main.py -sc <seasons>`
- Load dry run (no database): `python postgres_etl/main.py -sc <seasons> --dry-run`
- Quality report only: `python postgres_etl/main.py -sc <seasons> --quality-only`
- Per-game advanced stats (also run after every Silver load of game tables):
  `python postgres_etl/advanced.py -sc <seasons>`; `--dry-run` counts rows without
  writing, `--quality-only` checks the stored rows.
- Counted possessions from play-by-play (also run after a load of `games` or `play_by_play`):
  `python postgres_etl/possessions.py -sc <seasons>` (E2007+); `--dry-run` and `--quality-only`
  as above.
- Score flow from play-by-play (lead changes, time leading, runs, clutch; same triggers):
  `python postgres_etl/score_flow.py -sc <seasons>` (E2007+); `--dry-run` and `--quality-only`.
- Shot splits and shot zones (also run after a load of `games`, `play_by_play` or `shots`):
  `python postgres_etl/shot_splits.py -sc <seasons>` and
  `python postgres_etl/shot_zones.py -sc <seasons>` (E2007+); same options.
- On-court intervals per player from starters and substitutions (also run after a load of
  `games`, `game_player_stats` or `play_by_play`):
  `python postgres_etl/on_court.py -sc <seasons>` (E2007+); same options.
- Lineup stints (five-man stretches with possessions and points; same triggers):
  `python postgres_etl/lineups.py -sc <seasons>` (E2007+); same options.
- Build local Gold from Silver: `python gold_etl/main.py -sc <seasons>`
  (`-sc all` uses every locally loaded Silver season).
- Build only local standings: `python gold_etl/main.py -sc <seasons> -tb app_standings`
- Build local team and coverage tables: `python gold_etl/main.py -sc <seasons> -tb app_team_season_stats app_coverage_seasons app_coverage_games`
- Build local records and postseason series: `python gold_etl/main.py -sc <seasons> -tb app_records_player_seasons app_records_single_games app_records_team_seasons app_postseason_series`.
  Records use all loaded EuroLeague seasons regardless of `-sc`; series uses the selected seasons.
- Build local player and club identities: `python gold_etl/main.py -sc all -tb app_players app_club_identities`.
  Identities use every loaded Silver season for the selected competition, regardless of `-sc`.
- Build local cumulative team-round stats (local only, not published):
  `python gold_etl/main.py -sc <seasons> -tb team_round_stats`. `--quality-only` also
  prints `WARN` lines where final-round rows differ from the API team feeds.
- Build local team-round ratings (relative, SRS/SOS/SOV, adjusted; local only):
  `python gold_etl/main.py -sc <seasons> -tb team_round_ratings`.
- Build local team-round splits (home/away, last 5 and 10 games; local only):
  `python gold_etl/main.py -sc <seasons> -tb team_round_splits`.
- Build local player round stats (cumulative rates, per-100, Game Score, PIE; local only):
  `python gold_etl/main.py -sc <seasons> -tb player_round_stats`. `--quality-only` prints
  `WARN` lines where final-round rows differ from the API player feeds.
- Build local player PER (Hollinger PER per round, league mean 15; local only):
  `python gold_etl/main.py -sc <seasons> -tb player_round_ratings`. `--quality-only` checks
  the league-mean invariant.
- Build local player Win Shares (offensive, defensive, total and per 48; local only):
  `python gold_etl/main.py -sc <seasons> -tb player_round_win_shares`. `--quality-only`
  prints `WARN` lines where a scope round's total Win Shares is far from its games.
- Build local page-shaped team advanced stats (`app_standings_stats`, a per-round projection of
  the three team round tables; local only until 30g):
  `python gold_etl/main.py -sc <seasons> -tb app_standings_stats`. `--quality-only` ties each
  row to the stored team round tables.
- Build local play-by-play aggregates per club and scope (from the Silver tables of
  `possessions.py`, `score_flow.py`, `shot_splits.py`, `shot_zones.py`; local only):
  `python gold_etl/main.py -sc <seasons> -tb team_pbp_stats team_shot_zone_stats`.
  `--quality-only` checks that the `all` scope equals the sum of the phase scopes.
- Build local player on/off ratings per club and scope (from `lineups.py`; local only):
  `python gold_etl/main.py -sc <seasons> -tb player_on_off`. `--quality-only` checks that
  on plus off is one team total per club and scope.
- Build local 2, 3 and 5-man lineup ratings per club and scope (from `lineups.py`; local
  only): `python gold_etl/main.py -sc <seasons> -tb lineup_ratings`. `--quality-only` checks
  that the 2-man and 3-man rows each sum to ten times the 5-man rows.
- Build local RAPM per player and season (ridge fit over `lineups.py` stints; needs numpy
  in the Python environment; local only):
  `python gold_etl/main.py -sc <seasons> -tb player_rapm`.
- Traditional or misc table selections also rebuild their derived `PS` rows.
- Gold read-only source and derived counts: `python gold_etl/main.py -sc <seasons> --dry-run`
- Gold read-only equality checks: `python gold_etl/main.py -sc <seasons> --quality-only`
- List the 26 fixed Gold-to-Neon mappings: `python neon_publish/main.py --list-tables`
- Read-only Neon preflight and count preview: `python neon_publish/main.py -sc E2025 --dry-run`
- Publish one EuroLeague season and competition-wide Gold tables: `python neon_publish/main.py -sc E2026`
  after separate owner approval. The one-time
  [in-place migration](neon_publish/migrations/30f_in_place.sql) completed on
  2026-09-28. The publisher refuses incompatible schemas and
  scopes shrinking below 90% unless `--allow-shrink` is explicit. Failures roll
  back all selected scopes. `-tb` selects registered tables.
- CSV export: `python tables_to_csv/main.py -sc <seasons>`
- Test:
  - `cd api_requests && python -m unittest tests.test_scrapper`
  - `python -m unittest discover -s postgres_etl/tests`
  - `python -m unittest discover -s gold_etl/tests`
  - `python -m unittest neon_publish.tests.test_publish tables_to_csv.tests.test_csv_export`

There is no build, lint, format or typecheck step, no dependency file, and no
combined Verify command yet (build-plan item 17). Browser tests do not apply:
the project has no UI.
