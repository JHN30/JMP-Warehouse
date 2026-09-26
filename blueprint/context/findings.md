# Findings

> **Generated file.** The findings ledger: review findings raised by `/audit`
> against the work in progress, each with a durable ID, severity (P0-P3), and
> status. `/implement` marks repaired findings `fixed`, a later `/audit` pass
> moves them to `closed`, and `/complete` refuses to merge while any P0 or P1
> finding is `open` or `fixed`, then archives resolved findings with the work
> and resets this file.

### F-01 [P2] open - Game-night season-stats API answers are stored even when stale or empty

**File:** api_requests/scrapper.py:459
**Found:** 2026-09-25 from the owner's failed refresh (`logs/refresh/refresh_20260925_002852.log`)
**Why it matters:** On game nights the v3 season-stats endpoint returns
different answers to the same request. On 2026-09-24, after the last E2026 game
(ASV-TEL, 18:45 UTC), the lists alternated between 160 players (14 clubs,
correct), 136 (12 clubs, the state before that game) and 0, until at least
22:30 UTC. `fetch_to_cache` stores whatever arrives as the newest bronze
version, so the E2026 load mixed them (`traditional` all/perGame and `misc`
all/accumulated empty). The table-level shrink guard refused the publish
(`app_season_stats_misc` 640 -> 456) and Neon stayed unchanged, but it would
have let an empty `traditional` list through (456 -> 432). No quality check
notices an empty or inconsistent stats list.
**Suggested fix:** Deferred by the owner on 2026-09-25 ("we will find another
solution"). Facts for that later fix: for every season E2000-E2025 each season
and phase has all 8 category x mode lists, and the 4 categories have equal row
counts per season, phase and mode (only the bad E2026 load breaks this). An
absolute rule "stats clubs = clubs with box scores" does not hold (old per-game
lists only include qualifying players; club codes follow a player's latest
team). A first idea (refuse empty lists or fewer clubs than the stored version
at fetch, plus those two quality ERRORs) was written up and not built. Until
then: rerun the refresh the day after a game night, and never use
`--allow-shrink` for this.
**Resolution:**

### F-02 [P3] open - --drop-retired does not report individual missing names

**File:** postgres_etl/flat_schema.py:703
**Found:** 2026-09-26 by /audit independent (scope: current; lenses: quality, security, performance, tests)
**Why it matters:** The spec (Step 3) says the drop "reports names that are
missing ("already gone") or not a table (left alone)". `drop_retired_tables`
skips a missing name silently (`if kind is None: continue`) and only prints
"No retired tables left." when nothing at all was dropped. After a partial
earlier drop (or a table dropped by hand), the output lists only the remaining
tables and never says which of the listed names were already gone, so the
operator cannot confirm the full list was accounted for. Not a data risk: the
drop list and the transaction are correct.
**Suggested fix:** In the `kind is None` branch, log
`f"  {name}: already gone"` (keep the final "No retired tables left." line),
and extend the second-run test to assert one "already gone" line per name.
Alternatively, amend the spec wording if the quieter output is preferred.
**Resolution:**

### F-03 [P3] open - Loader --dry-run help says it never connects, but --drop-retired --dry-run does

**File:** postgres_etl/main.py:86
**Found:** 2026-09-26 by /audit independent (scope: current; lenses: quality, security, performance, tests)
**Why it matters:** `--dry-run` help reads "Read and validate rows without
connecting to PostgreSQL." Combined with the new `--drop-retired`, the dry run
connects to local PostgreSQL (`run_drop_retired` calls `connect(args.config)`)
and reads catalog and row counts. The `--config` help ("unused in --dry-run
mode") is likewise inaccurate for that combination. Read-only, so no data
risk, only misleading help text.
**Suggested fix:** Mention the exception in both help strings, for example
"... without connecting to PostgreSQL (with --drop-retired: list what would be
dropped, read-only)."
**Resolution:**
