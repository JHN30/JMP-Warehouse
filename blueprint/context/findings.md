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

### F-20 [P3] open - The Neon preflight looks up seasons with a hard-coded EuroLeague code

**File:** neon_publish/main.py:56
**Found:** 2026-10-26 during the feature 18 brief
**Why it matters:** the publish preflight checks `silver.seasons` with competition `E`
hard-coded. Harmless today, because the publisher refuses any other competition
(`neon_publish/publish.py:179`), but it must change when EuroCup publishing is approved.
**Suggested fix:** pass the competition through when EuroCup publishing is built; no
change needed before then.
**Resolution:**

### F-21 [P3] unverified - A points correction can leave the team total off the score while saying it was corrected

**File:** postgres_etl/raw_transform.py:536
**Found:** 2026-10-26 by /audit (scope: current; lenses: quality, security, performance, tests)
**Why it matters:** the corrected team total is the source total plus the players'
point changes, not a value checked against the score. That equals the score only when
the source total equals the sum of its players' points. Today it always does (0 team
totals differ from their player sums in either competition), so all three corrected
games end at their scores; a future source row with an inconsistent total would get a
`points` correction row while `team_points_differ_from_score` still fires.
**Suggested fix:** in `points_corrections`, correct a side only when its corrected
player points add up to the game score; otherwise leave it as given (the warnings
already show it). No current requirement would be lost.
**Resolution:**
