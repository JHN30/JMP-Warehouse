# Feature: Publish Completed Gold Tables

**From build-plan:** feature 30g
**Build attempt:** 1
**Status:** verified
**Branch:** `feature/publish-completed-gold-tables`

## Goal

Add the twelve new Gold tables of features 26-29 to the Neon publisher so they can be published for E2025 and E2026 like the other app tables. This item prepares and tests the code, the Neon migration SQL and the docs. Running the migration and the live publish on Neon stays a separate owner approval, after the web-app contract is agreed.

## In scope

- Table list (owner decision, all new Gold tables): `app_standings_stats`, `team_round_stats`, `team_round_ratings`, `team_round_splits`, `player_round_stats`, `player_round_ratings`, `player_round_win_shares`, `team_pbp_stats`, `team_shot_zone_stats`, `player_on_off`, `lineup_ratings`, `player_rapm`. The publisher's fixed list grows from 26 to 38 mappings; target names follow the existing rule (`app_` prefix unless already present), all season-scoped.
- Storage scope: E2025 and E2026 only, like the other app tables. The local size of these two seasons is about 66 MB; all seasons would be about 1.5 GB.
- A reviewed migration `neon_publish/migrations/30g_new_tables.sql` creating the twelve tables in `public` with the Gold column types and primary keys, generated from the Gold schema by `python neon_publish/main.py --print-migration`; a test keeps the file equal to the generated text. The recurring publisher never runs it.
- The refresh path (`pipeline.py` publishes with the fixed list) and the quality path (`neon_publish/main.py` checks every selected table before publishing) pick the new tables up through the contract; tests cover both.
- Docs: `neon_publish/README.md`, root `README.md`, `AGENTS.md`, `docs/DATA_DICTIONARY.md` (Neon names, "local only" notes), `gold_etl/schema.py` comments.

## Out of scope

- Running the migration or any publish on Neon, and any Neon connection (including a read-only dry run) in this item.
- The web-app changes in `jmp-euroleague2`, older seasons in Neon (item 15), and the Silver-derived tables (possessions, stints and so on), which stay local.
- Changes to the shrink guard, the atomic transaction or the per-game diff of play-by-play and shots.

## Build loop

Follow `workflow.stepReview: "feature"`; `workflow.checkpointCommits: "disabled"`; `/complete` creates the work commit.

## Build steps

- [x] **Step 1 - Contract and migration generator.** Extend the fixed list, add the DDL generator and `--print-migration`, commit the generated `30g_new_tables.sql`.
  *Done when:* unit tests cover 38 unique targets, the target-name rule, season scope for the new tables, the DDL for every new table (column types, NOT NULL, primary key), the file equalling the generator output, the `--list-tables` and `--print-migration` output and preflight reporting the new tables as missing; `python -m unittest neon_publish.tests.test_publish tables_to_csv.tests.test_csv_export` passes.
- [x] **Step 2 - Publish flow tests and docs.** Fake-connection tests that publish one new table, refresh and quality path checks, and the doc updates.
  *Done when:* a fake publish replaces one season slice of a new table and a wrong-type new table blocks it, the docs state 38 targets and that the migration and live publish need approval, and all declared suites pass.

## Files / areas

- `neon_publish/contract.py`, `neon_publish/main.py`, `neon_publish/migrations/30g_new_tables.sql` (new), `neon_publish/tests/test_publish.py`, `neon_publish/README.md`, `gold_etl/schema.py` (comments), `README.md`, `AGENTS.md`, `docs/DATA_DICTIONARY.md`.

## Data / contracts

- Neon tables `public.app_standings_stats`, `app_team_round_stats`, `app_team_round_ratings`, `app_team_round_splits`, `app_player_round_stats`, `app_player_round_ratings`, `app_player_round_win_shares`, `app_team_pbp_stats`, `app_team_shot_zone_stats`, `app_player_on_off`, `app_lineup_ratings`, `app_player_rapm` with the columns and keys of the Gold tables of the same name, replaced per competition and season in one transaction.
- Until the migration is applied, a live publish stops at the schema preflight ("missing table") and rolls back, leaving Neon unchanged and the refresh pending.

## Testing

- Unit tests only, with fake connections. No Neon connection is made in this item.

## Notes for the AI

- Do not connect to Neon. `project-plan.md` still says per-round player stats stay local because of storage; the owner has decided to publish them for E2025 and E2026, and updating that plan text is theirs.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":4562,"specSha256":"2a25ea395aac82376620b1745b2d2a787a451b6f9bddbe736234a5b5a6ba0804","branch":"refs/heads/feature/publish-completed-gold-tables","head":"7adf239fd969d32cd0fb745ef637a613298f5a26","baseRef":"refs/heads/main","baseCommit":"7adf239fd969d32cd0fb745ef637a613298f5a26","sourceTree":"e03292a45d4886ef583c10b685c06b871f0b6a67","absentOptional":[]} -->
