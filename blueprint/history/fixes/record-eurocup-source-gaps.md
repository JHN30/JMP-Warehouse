# Fix: Record EuroCup source gaps

**Type:** Fix
**Status:** verified
**Branch:** fix/record-eurocup-source-gaps
**Fixes:** F-16, F-17

## The problem

The owner accepted two unverified findings as source gaps on 2026-10-26, so neither is
fixed in code:
- **F-16:** live feeds with phantom substitution blocks skew on-court time and lineup
  stints in U2026 games 10 and 18.
- **F-17:** two official standings snapshots, U2011 VEF Riga at `L16` round 7 and U2025
  Hamburg at `RS` round 17, each miss one result for one round.

The decisions need a durable record, the Silver catalog should list both as EuroCup
quirks, and both ledger entries need archiving.

## The fix

Documentation and ledger only. There are no code, schema or data changes.

- `blueprint/context/findings.md`: F-16 and F-17 are `accepted`, each with the evidence
  and the owner's reason.
- `docs/SILVER_CATALOG.md` `## EuroCup` quirks gets one line per gap, naming the
  warnings that keep flagging them. The standings line explains that standings are not
  rebuilt from games, because official records can include deductions, such as E2022
  Panathinaikos's fair-play penalty.

## Build steps

- [x] 1. Record both decisions and add the two docs lines. This was committed as
  `b022543` on this branch before the spec was written, at the owner's request.
  **Done when:**
  - Both entries read `accepted` with a reason.
  - The relative-link check of `docs/SILVER_CATALOG.md` passes: 76 links, 0 broken.

## Verify

- `grep -n "^### F-1[67]" blueprint/context/findings.md` shows both as `accepted`.
- The EuroCup quirks in `docs/SILVER_CATALOG.md` list both gaps.
- No tests, because no code changed.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":1676,"specSha256":"e05133f285254a91e7fef4f7e2fa6610ee3e38079c66103f5cf2354f1885e40f","branch":"refs/heads/fix/record-eurocup-source-gaps","head":"b022543b02cc38807b139daaa13f3ac546f913bc","baseRef":"refs/heads/main","baseCommit":"47a2ec2970abba280bc920b5278a5c324ec49bd7","sourceTree":"7ced22b163adce9b5a0e0ec1354869e91509c53b","absentOptional":[]} -->

## Findings

### record-eurocup-source-gaps/F-16 [P3] accepted - New U2026 games have on-court time and lineup stint gaps

**File:** postgres_etl/on_court.py
**Found:** 2026-10-26 by the first `python pipeline.py -cp eurocup` refresh (feature 18b)
**Why it matters:** the games fetched that day added Silver warnings
`seconds_differ_from_box_score` (14 player rows) and
`stints_cover_little_of_the_game` (2 games) for U2026. If the reconstruction misreads
the current live play-by-play format, every new EuroCup game is affected.
**Suggested fix:** list the affected U2026 games, compare with EuroLeague E2026, and
check whether they are source gaps (missing substitutions) or a reconstruction defect.
**Resolution:** accepted 2026-10-26 by the owner's decision: it is a source gap, not fixed in code. Investigation, all read-only against local Silver: the 14 U2026 rows are all in games 10 and 18. E2026 has 0 such rows, U2025 has 12 over 195 games and E2025 has 4, so there is no format change. Game 18's feed logs a phantom substitution block at Q1 05:06 that repeats real substitutions made later (for example TRT IN 004469 at 05:06 and again at 04:16, and OUT 014900 at 05:06 and again at 02:53), and the players marked off keep playing. More inconsistencies follow later in the game. The reconstruction keeps the first of a repeated IN or OUT. An in-memory trial of the opposite rule, where the later repeat wins, changed U2026 from 14 to 13 rows and E2025 from 4 to 3, made E2010 worse (112 to 114), and still left each game 18 player about 294 s off. Reason for accepting: no simple rule repairs these feeds, and the existing `seconds_differ_from_box_score` and `stints_cover_little_of_the_game` warnings already flag the affected games. A docs line goes with the next fix.

### record-eurocup-source-gaps/F-17 [P3] accepted - EuroCup standings rows with games played not equal to wins plus losses

**File:** postgres_etl/quality.py:226
**Found:** 2026-10-26 during the EuroCup Silver quality runs
**Why it matters:** `standings_played_not_won_plus_lost` warns for 1 row in U2011 and 1
in U2025. Neither season has drawn games, so it is likely an API standings feed error,
but it is not yet confirmed which club and round.
**Suggested fix:** identify the two rows and compare them with the games; document them
as known source gaps or correct the derivation if Silver is wrong.
**Resolution:** accepted 2026-10-26 by the owner's decision: it is a source gap, not fixed in code. The two EuroCup rows are single-round glitches in the API standings snapshots. U2011 VEF Riga at L16 round 7 shows played 1 and 0-0, while the games give 0-1 and the next round shows 2 played and 0-2. U2025 Hamburg at RS round 17 shows played 17 and 2-14, while the games give 2-15 and the next round shows 18 played and 2-16. One result is missing from one snapshot, the played count already includes it, and the following rounds are right. The same warning also flags 3 EuroLeague rows, which are out of scope. One of them, E2022 Panathinaikos at round 34 (9-23), is correct: the owner confirmed 2 wins were deducted for a fair-play penalty. So rebuilding standings from the games would be wrong. The `standings_played_not_won_plus_lost` warning keeps flagging the rows.
