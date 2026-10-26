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

### F-11 [P3] fixed - The unattended missing-URL branch the scheduled run relies on has no unit test

**File:** pipeline.py:219
**Found:** 2026-10-24 by /audit independent (scope: current; lenses: quality, security, performance, tests)
**Why it matters:** the spec's unattended-safety contract is that the scheduled
run "never waits at a hidden prompt" and fails with "FAILED at Publish (missing
Neon URL)". The task action provides the non-console stdin (probe: the exact
action string gives `stdin.isatty()` False in a new hidden console, against True
without the empty pipe). The Python half is `resolve_neon_url`'s
`if not interactive: return None, ...` branch and `refresh`'s missing-URL return.
No test covers that case. Tests at neon_publish/tests/test_publish.py:765 and :870
pass `interactive=False` only with a URL present, and :843 only checks that the
prompt waits for Gold quality. If that guard regressed, `getpass` on Windows reads
the console directly, not stdin. The scheduled run would then hang in its hidden
window until the 2-hour limit, with no log result or summary. The code is correct
today; this is a coverage gap on behavior the feature now depends on.
**Suggested fix:** add one unit test that calls `refresh(build_parser().parse_args(["--skip-fetch"]), "E2025", ...)`
with a passing stage runner, `environ={}`, a missing `dotenv_path`,
`interactive=False` and a prompt that fails the test. Assert the result is
`(1, "FAILED at Publish (missing Neon URL)", ...)` and that `neon_publish/main.py`
never ran. No current requirement would be lost.
**Resolution:** fixed 2026-10-26 on fix/test-the-unattended-missing-neon-url-branch: added `test_unattended_run_without_neon_url_fails_without_prompting` in neon_publish/tests/test_publish.py (missing-URL failure, no prompt, no publish stage, pending kept); it fails when the `if not interactive` guard is removed.

### F-14 [P2] open - Silver accepts a team box score whose points do not match the game score

**File:** postgres_etl/quality.py:161
**Found:** 2026-10-26 by owner review during feature 18c (EuroCup postseason)
**Why it matters:** in U2005 game 4 (AMS 76-58 ASV, RS round 1) the source gives
ASV's Stephen Brun (`KSK`) 11 points and PIR 12 in 4 minutes with 0/1 twos, 0/1
threes and no free throws. ASV's team `total` row then says 69 points, while the game
result is 58 and ASV's makes add up to 58 (19x2 + 2x3 + 14). Nothing in Silver
compares team box-score points with the game score, so the wrong 69 flows into ASV's
per-game and per-round ratings and team totals; only Gold's
`true_shooting_pct below 0 or above 2` warning catches the player row. Owner wants
this fixed.
**Suggested fix:** add a Silver quality check for played games whose team `total`
points differ from `local_score`/`road_score` (and, as a second check, points that
differ from 2x two-pointers + 3x threes + free throws). Then decide with the owner
whether to correct a proven source error in Silver (for example points from the
shooting makes, recorded in `game_stat_gaps` or a corrections list) or only warn.
Run it over both competitions to see how many games are affected.
**Resolution:**

### F-15 [P3] unverified - On-court assist % above 100% for two EuroCup players

**File:** postgres_etl/advanced.py:309
**Found:** 2026-10-26 during feature 18a (EuroCup Gold), Silver warning `on_court_rate_out_of_range`
**Why it matters:** two on-court rows exceed the 0-1 range: U2008 game 32 player
`000529` (assist_pct 2.0, usage_pct 0.92, 1,912 s) and U2009 game 15 player `002042`
(assist_pct 1.67, 1,415 s). Either the on-court intervals miss part of the player's
time (so too few teammate baskets are counted), or the play-by-play is incomplete for
those games. The values reach `app_game_player_advanced` and the round tables.
**Suggested fix:** inspect both games' on-court intervals against box-score minutes and
the play-by-play; fix the reconstruction if it is wrong, otherwise keep the warning and
document the source gap.
**Resolution:**

### F-16 [P3] unverified - New U2026 games have on-court time and lineup stint gaps

**File:** postgres_etl/on_court.py
**Found:** 2026-10-26 by the first `python pipeline.py -cp eurocup` refresh (feature 18b)
**Why it matters:** the games fetched that day added Silver warnings
`seconds_differ_from_box_score` (14 player rows) and
`stints_cover_little_of_the_game` (2 games) for U2026. If the reconstruction misreads
the current live play-by-play format, every new EuroCup game is affected.
**Suggested fix:** list the affected U2026 games, compare with EuroLeague E2026, and
check whether they are source gaps (missing substitutions) or a reconstruction defect.
**Resolution:**

### F-17 [P3] unverified - EuroCup standings rows with games played not equal to wins plus losses

**File:** postgres_etl/quality.py:226
**Found:** 2026-10-26 during the EuroCup Silver quality runs
**Why it matters:** `standings_played_not_won_plus_lost` warns for 1 row in U2011 and 1
in U2025. Neither season has drawn games, so it is likely an API standings feed error,
but it is not yet confirmed which club and round.
**Suggested fix:** identify the two rows and compare them with the games; document them
as known source gaps or correct the derivation if Silver is wrong.
**Resolution:**

### F-18 [P3] unverified - EuroCup round totals differ slightly from the API feeds

**File:** gold_etl/quality.py:306
**Found:** 2026-10-26 during features 18a and 18c (EuroCup Gold quality)
**Why it matters:** 17 warnings in U2002-U2007 (`efg_pct`, `drb_pct`, 1-3 players or
clubs per season) and 4 in U2026 (`pir` and `turnovers` 1 off for 2 players) say our
box-score totals differ from the API's season feeds. The early ones are probably
source differences, the U2026 ones the live feed lagging behind corrected box scores,
but neither is proven.
**Suggested fix:** compare one example per season with the box scores; record the
known source gaps in the data dictionary, and re-check U2026 after a few refreshes.
**Resolution:**

### F-19 [P3] open - Data catalogs still describe EuroLeague only

**File:** docs/BRONZE_CATALOG.md:8
**Found:** 2026-10-26 during feature 18a (doc search)
**Why it matters:** `docs/BRONZE_CATALOG.md:8`, `docs/SILVER_CATALOG.md:9`,
`docs/DATA_CATALOG.md:8` and `docs/SILVER_TABLE_REFERENCE.md:8` say EuroCup coverage
will be documented later, although EuroCup is now in Bronze, Silver and Gold locally.
**Suggested fix:** add EuroCup coverage (U2002-U2026; U2000-U2001 empty in the API),
its phase codes and format eras, and its known source gaps to the catalogs.
**Resolution:**

### F-20 [P3] open - The Neon preflight looks up seasons with a hard-coded EuroLeague code

**File:** neon_publish/main.py:56
**Found:** 2026-10-26 during the feature 18 brief
**Why it matters:** the publish preflight checks `silver.seasons` with competition `E`
hard-coded. Harmless today, because the publisher refuses any other competition
(`neon_publish/publish.py:179`), but it must change when EuroCup publishing is approved.
**Suggested fix:** pass the competition through when EuroCup publishing is built; no
change needed before then.
**Resolution:**
