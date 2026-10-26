# Fix: Record EuroCup feed differences

**Type:** Fix
**Status:** verified
**Branch:** fix/record-eurocup-feed-differences
**Fixes:** F-18

## The problem

F-18 (unverified) asked whether the Gold quality warnings comparing EuroCup round totals
with the API season feeds point to a defect in our box-score totals. A read-only check on
2026-10-26 found none. Running
`python gold_etl/main.py -cp eurocup -sc 2002 2003 2004 2005 2006 2007 2026 -tb player_round_stats app_standings_stats --quality-only`
passed, and every warning falls into one of three causes:

| Seasons | Warning measures | Cause | Example checked |
|---|---|---|---|
| U2004, U2005 | `points`, `pir`, `points_for` and the shooting rates | F-14 corrections at load; the API feeds keep the source errors | ASV 743 vs 754 is Brun's corrected 11 points in U2005 game 4 |
| U2002, U2003, U2007 | `efg_pct`, `drb_pct` | the API's own rate columns; every counting stat matches its traditional feed | BQC (U2002): points, 2s, 3s, DRB, TO and PIR all equal; eFG% from those counts is 64.6, the API shows 59.8 |
| U2026 | `pir`, `turnovers` | the season feed is one turnover behind the box scores | 006872: box 4 TO across games 11, 26, 44 and 57, play-by-play `TO` events 4, feed 3 |

The owner chose to mark F-18 `invalid`, since there is no defect, and to document the
causes.

## The fix

Documentation and ledger only. There are no code, schema or data changes.

- In `blueprint/context/findings.md`, mark F-18 `invalid`, with the evidence above in
  **Resolution**.
- Add one line to the `## EuroCup` source quirks in `docs/SILVER_CATALOG.md`: the Gold
  warnings that compare round totals with the API season feeds are expected in these
  seasons, for the three causes above. Keep the line short and link nothing new.

## Build steps

- [x] 1. Mark F-18 `invalid` with the evidence, and add the docs line.
  **Done when:**
  - `grep -n "^### F-18" blueprint/context/findings.md` shows `invalid`.
  - The EuroCup quirks list the feed differences.
  - The relative-link check of `docs/SILVER_CATALOG.md` passes.

## Verify

- The grep and link check above.
- No tests, because no code changed.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":2157,"specSha256":"f40b7431afa859bd339e9cfe38aac350928c102d7afcf9d77619346b2a78f47c","branch":"refs/heads/fix/record-eurocup-feed-differences","head":"5e54b0ff7db7a30a1328b37a52e6de6b65768f3b","baseRef":"refs/heads/main","baseCommit":"5e54b0ff7db7a30a1328b37a52e6de6b65768f3b","sourceTree":"56a15608965c908a1991eb012745e489bd11ce0e","absentOptional":[]} -->

## Findings

### record-eurocup-feed-differences/F-18 [P3] invalid - EuroCup round totals differ slightly from the API feeds

**File:** gold_etl/quality.py:306
**Found:** 2026-10-26 during features 18a and 18c (EuroCup Gold quality)
**Why it matters:** 17 warnings in U2002-U2007 (`efg_pct`, `drb_pct`, 1-3 players or
clubs per season) and 4 in U2026 (`pir` and `turnovers` 1 off for 2 players) say our
box-score totals differ from the API's season feeds. The early ones are probably
source differences, the U2026 ones the live feed lagging behind corrected box scores,
but neither is proven.
**Suggested fix:** compare one example per season with the box scores; record the
known source gaps in the data dictionary, and re-check U2026 after a few refreshes.
**Resolution:** invalid 2026-10-26: there is no defect in our data, confirmed by the owner's call after a read-only check. `gold_etl/main.py -cp eurocup -sc 2002 2003 2004 2005 2006 2007 2026 -tb player_round_stats app_standings_stats --quality-only` passed, and every warning has one of three causes. (1) In U2004 and U2005, `points`, `pir`, `points_for` and the shooting rates differ because of the F-14 corrections at load; the API feeds keep the source errors (for example ASV 743 vs 754 is Brun's corrected 11 points in U2005 game 4). (2) In U2002, U2003 and U2007, `efg_pct` and `drb_pct` are the API's own rate columns. Every counting stat matches its traditional feed: for BQC in U2002, points, 2s, 3s, DRB, TO and PIR are all equal, and eFG% from those counts is 64.6 against the API's 59.8. (3) In U2026, the season feed is one turnover behind: 006872 has 4 TO in the box scores (games 11, 26, 44 and 57) and 4 `TO` events in the play-by-play, while the feed fetched at 16:11 has 3. The warnings correctly show feed disagreements.
