# Feature: EuroCup refresh command

**From build-plan:** feature 18b
**Build attempt:** 1
**Type:** Feature
**Status:** verified
**Branch:** feature/eurocup-refresh-command

## Goal

`python pipeline.py -cp eurocup` refreshes the current EuroCup season only: fetch,
Silver load, Gold build and Gold quality, and never connects to Neon. EuroLeague's
`python pipeline.py` is unchanged, including its live publish.

## In scope

- A EuroCup refresh (`-cp eurocup`, current or a chosen season) has no publish
  stage. After Gold quality passes it ends with result `OK (local only)`, exit 0,
  and `Publish:  skipped` in the summary. It never resolves or prompts for a Neon
  URL (no environment or `.env` lookup) and never starts `neon_publish/main.py`.
  Today the same command would reach the publisher, which refuses EuroCup
  ([neon_publish/publish.py:179](../../neon_publish/publish.py#L179)).
- The "nothing changed" skip works for EuroCup. Today the skip test is
  `publish_pending` ([pipeline.py:385-388](../../pipeline.py#L385-L388)), which only
  a live publish clears, so a never-published EuroCup season would rebuild every
  day. For EuroCup the refresh uses a `local_pending` state key instead: set to
  true when the fetch changed something and before the load starts, cleared when
  Gold quality passes. A failed stage leaves it true, so the next run retries.
- EuroCup runs still set `publish_pending` when data changes and never clear it, so
  a later approved EuroCup publish knows which seasons need sending.
- `--dry-run-publish` and `--allow-shrink` are rejected with `-cp eurocup`
  (`parser.error`), since a EuroCup refresh has no publish.
- Docs: AGENTS.md Commands and README.md refresh section.

## Out of scope

- Any change to the EuroLeague refresh: `python pipeline.py` keeps its stages,
  results, state handling and live publish.
- A general skip-publish option.
- The scheduled task (`register_refresh_task.ps1` and its registration), left for
  later and not in the build plan yet.
- `--all` (already local only for both competitions).
- EuroCup Neon publishing, which comes back as its own feature after the owner
  approves it, and EuroCup postseason outputs (18c).

## Build loop

`workflow.stepReview` is `feature` and checkpoint commits are disabled: build all
steps, then present one review packet. `/complete` makes the feature commit.

## Build steps

- [x] 1. **Local-only EuroCup refresh in `pipeline.py`.** The competition check in
  `refresh`, the `local_pending` skip test and state writes, the early return after
  Gold quality, and the two argument rules in `main`. Tests in
  `neon_publish/tests/test_publish.py` `PipelineTests`, in the style of the
  existing `refresh` tests:
  - EuroCup run: stages are load, Gold build, Gold quality only; the prompt is never
    called (it fails the test); result `(0, "OK (local only)")`; `publish_pending`
    true and `local_pending` false afterwards; summary shows `Publish:  skipped`;
  - EuroCup with nothing changed and `local_pending` false: `NOTHING TO DO`, no
    stages, even when `publish_pending` is true;
  - EuroCup with a failed Gold quality keeps `local_pending` true;
  - `-cp eurocup` with `--dry-run-publish` or `--allow-shrink` exits with a parser
    error;
  - the existing EuroLeague tests pass unchanged.
  **Done when:** the publisher/CSV suite passes with the new tests.
- [x] 2. **Run the EuroCup refresh for real, then update the docs.**
  `python pipeline.py -cp eurocup` (current season U2026), then run it again.
  **Done when:** the first run ends `OK (local only)` with 0 Silver and Gold quality
  errors and no Neon line in its log; the second ends `NOTHING TO DO` unless the
  fetch found a change; `data/state/pipeline_eurocup_U2026.json` holds
  `local_pending: false`; AGENTS.md and README.md describe the command.

## Files / areas

- `pipeline.py` (`refresh`, `main`)
- `neon_publish/tests/test_publish.py` (`PipelineTests`)
- `AGENTS.md`, `README.md`

## Data / contracts

- State file `data/state/pipeline_<competition>_<season>.json` (local, not
  committed): EuroCup files gain `local_pending` (bool). A missing key reads as
  true, so the first EuroCup refresh always builds. EuroLeague files are untouched.
- `OK (local only)` is a new result string for EuroCup runs only; every EuroLeague
  result string stays the same.

## Testing

- `python -m unittest neon_publish.tests.test_publish tables_to_csv.tests.test_csv_export`
  (pipeline tests live there), then all declared suites.
- The live run in step 2 fetches from the EuroLeague API at the usual 2.5 s
  interval and writes only local Silver, Gold and state; it never connects to Neon.

## Notes for the AI

- Keep the unattended contract: a EuroCup run never prompts, and never reads a Neon
  URL from the environment or `.env`.
- Reuse `refresh()`'s `(code, result, next_step)` return and `build_summary`, which
  already prints `Publish:  skipped` when no publish lines exist.
- Live runs (2026-10-26): `python pipeline.py -cp eurocup` ended `OK (local only)`
  in 2 min 54 s (61 changed resources, 60,080 rows loaded, Silver quality 0 errors,
  Gold built and quality checked, no Neon line in the log); state then held
  `publish_pending: true`, `local_pending: false`. The second run ended
  `NOTHING TO DO` in 1 s. New U2026 Silver warnings from the fetched games:
  `seconds_differ_from_box_score` (14), `stints_cover_little_of_the_game` (2),
  `attendance_not_recorded` (6).


<!-- blueprint:completion {"schemaVersion":1,"specBytes":5580,"specSha256":"a08b947c113eb5cb0cb38457fa7a9376dfc1b7675a3ec6a6cf42fe1924f10438","branch":"refs/heads/feature/eurocup-refresh-command","head":"4ba8e01cc3a3b063f1aee1f0f2085a0537d626de","baseRef":"refs/heads/main","baseCommit":"4ba8e01cc3a3b063f1aee1f0f2085a0537d626de","sourceTree":"48c7133c0a6d593e95b5894c77c68eaca0339a75","absentOptional":[]} -->
