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
