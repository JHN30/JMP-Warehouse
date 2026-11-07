# Fix: Unreadable play-by-play clock

**Type:** Fix
**Status:** verified
**Branch:** fix/unreadable-play-by-play-clock

## The problem

The 2026-11-07 refreshes (06:00 and 11:58) both stop at Load with
`ETL failed: A string literal cannot contain NUL (0x00) characters.` while
loading E2026 `play_by_play`, so Gold and the Neon publish did not run.

The live play-by-play for E2026 game 100 (Olympiacos vs Crvena Zvezda, not
live) has binary junk in `MARKERTIME` on 19 of its 496 events, for example
`'\x01\x05.\x00'` and `'\x01\x10.\x00'` instead of `MM:SS`. They are the
substitutions at the start of Q3 and Q4, the last one or two plays of Q1 to Q3,
and two single plays (Q1 near 06:0x, Q4 near 08:0x). A fresh API request
returns the same bytes, so a refetch does not help.

`marker_time` is a plain `TEXT` field (`postgres_etl/flat_schema.py`,
`MARKERTIME`), so `cast` passes the string through and psycopg2 rejects the
NUL. Other odd source values (`ND`, `00:-1`, `-1:00`) are already stored
verbatim and ignored by the clock readers, but a NUL cannot be stored at all.
Every NULL `marker_time` today belongs to a `BP`, `EP` or `EG` row.

## The fix

- Derive `marker_time` in `raw_transform.py` (`@marker_time`): the source
  value, or NULL when it contains a control character (below U+0020 or
  U+007F). Readable values, including `ND` and `00:-1`, stay verbatim.
- Keep the gap visible with a quality `WARN`,
  `play_by_play_clock_unreadable`: rows with NULL `marker_time` whose play
  type is not `BP`, `EP` or `EG`. It is 0 for every season loaded today and 19
  for E2026 after the fix.
- Must not break: every other stored `marker_time` stays identical; the
  clock readers (`possessions._clock`, `on_court`, `lineups`,
  `on_court_rates`, `score_flow`) already treat a missing clock as unknown;
  game 100 must not become a `play_by_play_without_clock` game. No schema
  change, no new dependency, bronze untouched.
- Docs: note the rule and the warning where `marker_time` and the quality
  warnings are described (`docs/SILVER_CATALOG.md`, `docs/DATA_DICTIONARY.md`
  if it lists the column).

## Build steps

- [x] 1. **Unreadable clocks stored as NULL, with a warning.** Add the derived
  field and the `WARN` check. Tests in `postgres_etl/tests/`: a `MARKERTIME`
  with NUL or other control characters becomes NULL; `05:59`, `ND`, `00:-1`
  and an empty value behave as before; the new check is registered as `WARN`
  when `play_by_play` is selected and its SQL skips `BP`, `EP` and `EG`.
  Update the docs.
  Done when: the four test commands in `AGENTS.md` pass;
  `python postgres_etl/main.py -sc E2026` loads with 0 quality errors and
  `play_by_play_clock_unreadable` = 19; the same check is 0 for the other
  loaded EuroLeague seasons; and the E2026 per-game Silver steps
  (`advanced.py`, `possessions.py`, `score_flow.py`, `shot_splits.py`,
  `on_court.py`, `lineups.py`) and `gold_etl/main.py -sc E2026 --quality-only`
  after a local Gold build pass.

## Verify

- Read-only SQL: game 100 has 496 `play_by_play` rows, 19 with NULL
  `marker_time`, and `marker_time` for all other E2026 games matches the
  values before the reload.
- `python pipeline.py --dry-run-publish` reaches Publish (dry run) with no
  remote writes. The live publish is left to the next scheduled 06:00 run or
  an owner-run `python pipeline.py`.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":3351,"specSha256":"fb32585552224ad7a18c677613943b9b7d484c83ff845d627fcb3724688491c4","branch":"refs/heads/fix/unreadable-play-by-play-clock","head":"1bb93d98b1314074aaf9cd0b5f888466dcabcbd7","baseRef":"refs/heads/main","baseCommit":"1bb93d98b1314074aaf9cd0b5f888466dcabcbd7","sourceTree":"9791a8b9f47f6331155df42910cd2151e5a50dea","absentOptional":[]} -->
