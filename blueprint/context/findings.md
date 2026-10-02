# Findings

> **Generated file.** The findings ledger: review findings raised by `/audit`
> against the work in progress, each with a durable ID, severity (P0-P3), and
> status. `/implement` marks repaired findings `fixed`, a later `/audit` pass
> moves them to `closed`, and `/complete` refuses to merge while any P0 or P1
> finding is `open` or `fixed`, then archives resolved findings with the work
> and resets this file.

### F-05 [P3] unverified - A legitimate correction that lowers an accumulated feed would be refused

**File:** api_requests/scrapper.py:497
**Found:** 2026-09-27 by /audit (scope: current; lenses: quality, security, performance, tests)
**Why it matters:** the guard treats any drop in clubs or total games of an
accumulated feed as stale. If EuroLeague ever corrects a feed downward (for
example removing a duplicated player or an annulled game), the correction is
refused until later games lift the totals above the stored ones. After the
season's last game that never happens, so the stored version would stay. No
such correction has been observed; the manifest keeps the refused answer.
**Suggested fix:** none needed unless it happens. If it does, the `rejected`
manifest records show it; a one-off manual re-fetch without the guard (or a
`--refresh-current` override flag) would accept the correction.
**Resolution:**

### F-08 [P3] unverified - The roughly 25 MB Neon size for 30h-30j is an estimate, not a measurement

**File:** blueprint/context/current-feature.md:76
**Found:** 2026-10-02 by /audit (scope: current; lenses: quality, security, performance, tests)
**Why it matters:** the figure comes from Silver table sizes scaled by row counts. Neon was
153 MB of the 512 MB free tier when measured, so there is headroom, but nothing has been
published yet to confirm the real size, including primary-key index overhead.
**Suggested fix:** after the migrations are applied and E2025 and E2026 are published,
compare `pg_database_size` with the 153 MB baseline.
**Resolution:**

### F-09 [P3] open - The dictionary's per-game paragraph points at sections that do not exist for all nine tables

**File:** docs/DATA_DICTIONARY.md:518
**Found:** 2026-10-02 by /audit (scope: current; lenses: quality, security, performance, tests)
**Why it matters:** the new "Nine per-game tables" paragraph says each table "is defined in its
own section below (see 'Derived per-game advanced tables' and the `game_team_*` and
`game_player_on_court` sections)". `game_stat_gaps` has no section of its own (it is defined in
the Silver table list and the stat-name notes), and `game_player_on_court` is the only on-court
section the pointer names although `game_team_lineup_stints` has one too. The same paragraph has
one source line over 150 characters where the neighbours wrap near 90.
**Suggested fix:** name the exact sections ("Derived per-game advanced tables", `game_team_possessions`
through `game_team_lineup_stints`, and the Silver table list for `game_stat_gaps`) and rewrap the
long line. No current requirement would be lost.
**Resolution:**

### F-10 [P3] open - The same paragraph says the tables are published to Neon without the migration qualifier

**File:** docs/DATA_DICTIONARY.md:519
**Found:** 2026-10-02 by /audit (scope: current; lenses: quality, security, performance, tests)
**Why it matters:** the paragraph states the nine tables are "published to Neon as
`public.app_<name>` for E2025 and E2026", while each per-table section (and the Neon contract
paragraph) adds "once the reviewed migration is applied". Until the owner applies the 30h, 30i and
30j migrations and publishes, the flat statement is untrue. It becomes accurate after publishing.
**Suggested fix:** add "once their reviewed migrations are applied" to the sentence, or leave it
and re-read it after the first publish.
**Resolution:**
