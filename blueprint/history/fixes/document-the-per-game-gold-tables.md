# Fix: Document the per-game Gold tables

**Type:** Fix
**Status:** verified
**Branch:** fix/document-the-per-game-gold-tables

## The problem

Features 30h, 30i and 30j added nine per-game Gold tables, but three overview texts still
describe the old state:

- [gold_etl/README.md](gold_etl/README.md) says Gold "copies 16 source tables", never mentions
  the nine new tables or their `-tb` commands, and ends with "Publishing remains paused", which
  has been false since 30f.
- The "Local Gold source tables" section of
  [docs/DATA_DICTIONARY.md](docs/DATA_DICTIONARY.md) lists only the 16 original tables, so a
  reader looking for what Gold contains does not find the seven copied and two derived per-game
  tables.
- The "What this is" paragraph in [AGENTS.md](AGENTS.md) describes Gold as the 16 source tables
  plus the older derived tables, with no mention of the per-game tables.

## The fix

Text only, no code and no behavior change:

- **gold_etl/README.md:** add a short paragraph naming the nine tables in three groups (derived
  `game_player_advanced` and `game_team_advanced`; copies `game_team_possessions`,
  `game_team_score_flow`, `game_team_shot_splits`, `game_team_shot_zones`; copies
  `game_player_on_court`, `game_team_lineup_stints`, `game_stat_gaps`), say the copies keep Silver
  names, values, NULLs, types and keys without `load_id`/`loaded_at`, and add the three `-tb`
  commands to the command block. Replace "Publishing remains paused." with a sentence pointing to
  [neon_publish/README.md](neon_publish/README.md) (Gold never writes Neon; publishing is a
  separate, owner-approved step). Change "copies 16 source tables" wording so it does not claim
  to be the only copies.
- **docs/DATA_DICTIONARY.md:** after the 16-table paragraph of "Local Gold source tables", add one
  paragraph listing the seven copied per-game tables (30i and 30j) and the two derived ones (30h)
  with a pointer to the sections that define them; fix the sentence "The other 12 Silver tables
  ... are not copied by 30a" so it stays true (30a still copies only the 16).
- **AGENTS.md:** extend the "What this is" sentence so Gold also includes the nine per-game tables
  and the later round, play-by-play and lineup tables are not implied to be absent. Keep the
  paragraph short; do not change the Commands section.
- The root [README.md](README.md) summary of the Gold stage said "copies 16 source tables" too, so it
  gets the same one-sentence correction (added during implementation).
- Must not change: any code, test, migration or generated count that is already correct. Counts
  stay 16 source tables, 47 Neon targets.

## Build steps

- [x] 1. **Update the three texts.** Edit the three files as described. *Done when:* a search of
  all non-archive markdown for "Publishing remains paused" and for "copies 16 source tables"
  finds nothing, each of the nine table names appears in the Gold README and in the "Local Gold
  source tables" section, and `python -m unittest discover -s gold_etl/tests` still passes
  (nothing but text changed, so `git diff --stat` shows only the three markdown files plus
  the fix archive and ledger at completion).

## Verify

- `grep -rn "Publishing remains paused" --include=*.md . ` returns nothing outside
  `blueprint/history`.
- The nine table names are present in `gold_etl/README.md` and `docs/DATA_DICTIONARY.md`.
- The four test commands in `AGENTS.md` pass (documentation-only change).


<!-- blueprint:completion {"schemaVersion":1,"specBytes":3453,"specSha256":"808f2864d60c1be33727acd8bc8668f1a554024ea5dc875b4bb91d37f6b527b7","branch":"refs/heads/fix/document-the-per-game-gold-tables","head":"296845a79fd9cdbf447e316f5e990a92dc7af877","baseRef":"refs/heads/main","baseCommit":"296845a79fd9cdbf447e316f5e990a92dc7af877","sourceTree":"c30e2b5cf002d3411ae1dfe044194e2acdd9fd69","absentOptional":[]} -->
