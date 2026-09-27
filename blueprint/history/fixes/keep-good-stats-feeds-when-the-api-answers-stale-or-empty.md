# Fix: Keep good stats feeds when the API answers stale or empty

**Type:** Fix
**Status:** verified
**Branch:** `fix/keep-good-stats-feeds-when-the-api-answers-stale-or-empty`
**Fixes:** F-01, F-04

## The problem

On game days the v3 statistics endpoints answer the same request differently:
the full list, an older shorter list, or nothing. Seen for players on
2026-09-24 (160 / 136 / 0 players, 14 / 12 / 0 clubs) and for teams on
2026-09-27 (E2026 `all` `perGame` empty, then full; `RS` empty in both modes
while `opponents_traditional` `RS` held 14 of 20 clubs). This is a EuroLeague
API problem and it corrects itself on a later request.

`fetch_to_cache` in `api_requests/scrapper.py` stores whatever arrives as the
newest bronze version, so a worse answer replaces a good one and the loader
loads it. An empty feed is flagged (`season_stats_phase_mode_missing`), but a
smaller or partial answer passes without any message.

## The fix

Owner decision (2026-09-27): per endpoint, new data that looks fine is stored
as usual. A feed whose new answer is worse keeps its previous good version, and
the run says so.

**1. Keep the good version, with a warning.** This applies to the v3
season-stats feeds only (the 4 player and 4 team feeds), when one is fetched
again and a version is already stored:

- The new answer is **worse** when it has fewer distinct clubs than the stored
  version, or, for an `accumulated` feed, a lower sum of `gamesPlayed`. Within a
  season neither can legitimately go down. The club of a player row is
  `player.team.code`; of a team row, `team.code`.
- A worse answer is not stored as the newest version: the previous one stays
  the latest, so the loader keeps using it. The answer is still recorded in the
  bronze manifest (`manifest.jsonl`) with URL, parameters, status code,
  `stored_as: null` and a `rejected` reason, so bronze keeps a record of every
  answer received.
- The run prints
  `[kept]    <resource>: API answered <new> clubs / <games> games, stored version has <old> / <games>; kept the stored version, refresh again later`
  and the run summary shows "Stats feeds kept from an earlier fetch: N". This
  is not a failed request and does not count toward the failure limit.
- Every other feed in the same run is stored normally.
- A first fetch (nothing stored yet) is stored as today; an empty first answer
  is still flagged by the loader's missing-feed warning.

**2. Partial-feed quality warning.** Add `season_stats_feed_partial` (WARN) in
`postgres_etl/quality.py` for the 4 player and 4 team season-stats tables. It
counts (phase, mode) feeds with rows whose distinct clubs are fewer than the
clubs with played games in that phase (`all`: any phase). The derived `PS` rows
are excluded. Known historical source gaps it flags, such as the opponents feeds
of E2000 `PO` and E2008-E2015 `all` accumulated, are listed in the data
dictionary.

**3. Repair E2026.** Once the guard exists, re-fetch the current season's
stats with `--refresh-current` (again later in the day if the API is still
partial; the guard keeps the good versions), then load E2026.

**Must not break:**
- feeds that grow normally, stored on every refresh;
- every other resource (game lists, box scores, standings and the rest are
  untouched);
- completed seasons (not fetched again, so the check never applies);
- the existing missing-feed warning and the Neon shrink guard.

## Build steps

- [x] **Step 1 - Keep the good version** - add the comparison, the `[kept]` path
  with the manifest record, and the summary count (`api_requests/scrapper.py`,
  `api_requests/main.py`). Tests with the fake client:
  - a second answer with fewer clubs is kept out and the first stays latest;
  - an accumulated answer with fewer total games played is kept out;
  - a bigger answer replaces the old one;
  - in the same run, a worse feed is kept while a good feed is stored;
  - an empty first answer is stored;
  - other resources are not checked.

  *Done when:* `cd api_requests && python -m unittest tests.test_scrapper`
  passes.
- [x] **Step 2 - Partial-feed warning and docs** - add `season_stats_feed_partial`
  with tests. Run `python postgres_etl/main.py -sc all -tb <the 8 season-stats
  tables> games --quality-only` and list every flagged season and feed in
  `docs/DATA_DICTIONARY.md`. Describe the kept-version rule in
  `api_requests/README.md` (Refreshing). *Done when:* the loader tests pass and
  every flagged feed is explained.
- [x] **Step 3 - Repair E2026** - `python api_requests/main.py -sc 2026 -ds
  game_lists season_stats --refresh-current`, then `python postgres_etl/main.py
  -sc 2026`. *Done when:* E2026 has no missing-feed or partial-feed warning, or
  the remaining ones are listed as the API's current answer. Neon is not
  published here; the next normal refresh publishes.
- [x] **Step 4 - Show kept feeds in the pipeline summary (F-04)** - `pipeline.py`
  reads `kept_resources` from the fetch summary (empty when absent) and adds
  them under the `Fetch:` line of the Refresh summary and to the log line. Test
  in `neon_publish/tests/test_publish.py`. *Done when:* the publish/pipeline
  tests pass and the summary lists kept feeds only when there are any.

## Verify

- All three test commands pass.
- `python postgres_etl/main.py -sc 2026 --quality-only`: no
  `season_stats_phase_mode_missing` or `season_stats_feed_partial` warning for
  E2026, or only listed ones.
- On a game day, `python pipeline.py --dry-run-publish` shows `[kept]` lines for
  any feed the API answered badly, while the other feeds update.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":5687,"specSha256":"4ad50f97540905800aacc48a307a2c17ef8fb96f57e4ba5f8b765440b120f8f4","branch":"refs/heads/fix/keep-good-stats-feeds-when-the-api-answers-stale-or-empty","head":"5d3a8a3cee17b8e4ba300a2b1e890efa5a48a0da","baseRef":"refs/heads/main","baseCommit":"5d3a8a3cee17b8e4ba300a2b1e890efa5a48a0da","sourceTree":"17434dd33314d9792744a5f3b3cc5d30c481cd08","absentOptional":[]} -->

## Findings

### keep-good-stats-feeds-when-the-api-answers-stale-or-empty/F-01 [P2] closed - Game-night season-stats API answers are stored even when stale or empty

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
**Resolution:** fixed on 2026-09-27 by fix/keep-good-stats-feeds-when-the-api-answers-stale-or-empty; closed by /audit current on 2026-09-27. `fetch_to_cache(keep_if_worse=True)` (api_requests/scrapper.py) now refuses a re-fetched accumulated feed with fewer clubs or fewer total games and an empty per-game feed, logs it in the manifest and keeps the stored version (7 tests; live E2026 run kept 10 bad answers). `season_stats_feed_partial` warns on partial accumulated feeds. By design a shorter but non-empty per-game answer is still stored (per-game feeds shrink legitimately); new entries F-04 and F-05 cover the rest.

### keep-good-stats-feeds-when-the-api-answers-stale-or-empty/F-02 [P3] accepted - --drop-retired does not report individual missing names

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
**Resolution:** accepted by the owner on 2026-09-27: the one-time cleanup is already completed in both databases, and this concerns output wording only. The one-time commands are to be removed in feature 16.

### keep-good-stats-feeds-when-the-api-answers-stale-or-empty/F-03 [P3] accepted - Loader --dry-run help says it never connects, but --drop-retired --dry-run does

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
**Resolution:** accepted by the owner on 2026-09-27: the one-time cleanup is already completed in both databases, and this concerns output wording only. The one-time commands are to be removed in feature 16.
