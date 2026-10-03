# Fix: Detect stale stats feeds against the v2 games and try fallback keys

**Type:** Fix
**Status:** verified (all steps; four test commands pass; live refresh ran 2026-10-03 with 0 feeds behind; local load and Gold built, Neon not published)
**Branch:** `fix/detect-stale-stats-feeds-against-v2-games-and-try-fallback-keys`

Builds on `fix/keep-good-stats-feeds-when-the-api-answers-stale-or-empty`
(F-01). Related, not stamped: F-05 (a legitimate downward correction would be
refused; unchanged by this fix).

## The problem

The first fix only compares a new answer with the stored copy, so an answer
that is stale but not worse is stored and reported as fine. Investigated on
2026-10-03 (bronze manifests, 9 refresh logs and about 90 read-only requests):

- **The API caches a snapshot per query key, and some keys are frozen.** The
  same key returned identical bytes for 5+ minutes (polled every minute), also
  with a different User-Agent, `Origin`, `Cache-Control: no-cache`, another
  `Limit` or a new `_` value. The Sep 24 22:05Z snapshot (sha `ddd06583`, 12
  clubs, 1 game each) is still served for the E2026 `RS` player keys 9 days
  later. Cloudflare is not the cause (`max-age=60`, `cf-cache-status: MISS`,
  `x-cache-hits: 0`); the `_` parameter busts Cloudflare but not the origin.
- **Other keys of the same data are fresh.** With `SeasonMode=Range`,
  `FromSeasonCode=ToSeasonCode=E2026` and the same other parameters, about 20 of
  the 32 feeds returned every club at 3 games while the canonical key was
  stale. Removing the sort parameters or reversing `SortDirection` also changes
  the snapshot, but it changes `player_ranking` and `entry_ordinal`, so it is
  not used.
- **Retries recover only sometimes.** On Oct 1 and Oct 2 almost every stale feed
  recovered after 1-7 retries; on Oct 3 none of 22 feeds did, in two runs.
- **The guard has blind spots.** `perGame` feeds are only refused when empty
  (`teams_traditional_RS_perGame` was saved with every club at 2 games and
  logged `[same]`), and `[same]` on `teams_traditional_RS_accumulated` hid a
  copy that is 6 games behind (48 of 60 team-games; games 25-30 of Oct 2 were
  missing while v2 and the standings had them). `min_clubs` only counts clubs.
- **Multi-club codes.** Fresh data has `team.code = "BAS;TEL"` (a player who
  moved clubs). Silver keeps it verbatim in `club_code`: 95 such codes already
  exist in bronze since E2001, so the loader needs no change. The fetcher,
  however, counts it as a club in `stats_feed_size`, so a fresh answer
  with 21 "clubs" stored next to a stale one with 20 can make the next fresh
  answer look worse (20 < 21) and be refused.

## The fix

All in `api_requests/scrapper.py` (the fetch layer); Silver and Gold are not
touched. Ground truth is the v2 game list, which is already fetched first.

**1. Completeness against v2.** For each scope (`all` or a phase), count the
played games per club from the v2 list. A v3 stats answer is *complete* when
every one of those clubs is present and:

- team feeds (4): each club's `gamesPlayed` equals its played games, in both
  `perGame` and `accumulated` modes;
- player feeds (4): each club's highest player `gamesPlayed` equals its played
  games (per-game feeds list only players with more than half of the games, but
  someone plays every game).

Clubs whose code contains `;` are ignored for the club set and for this check.
This replaces `min_clubs` and applies to every v3 stats feed, so a stale answer
that is not worse than the stored one is no longer accepted silently.

**2. What is stored.** An answer is stored when it is complete and not worse
than the stored version by the existing rule. An incomplete answer is stored
only when it is also not worse and covers at least as many club-games (sum over
the scope's clubs of `min(gamesPlayed, played games)`) as the stored version, so
partial progress is kept and a regression such as a Sep 24 snapshot replacing a
newer one is not. Otherwise the stored version stays, as today. With no stored
version the last answer is stored, as today.

**3. Retries and fallback keys.**
- `STALE_RETRIES` goes from 8 to 4: recoveries in the logs came mostly within 4
  retries, and a key that is frozen did not change within minutes, so waiting
  between retries was not adopted.
- When the answer is still not complete after the retries (and a complete stored
  version does not already exist), the same feed is requested under fallback
  keys, one request each, and the first complete, not-worse answer is stored
  under the normal bronze resource name:
  1. same parameters with `SeasonMode=Range`, `FromSeasonCode` and
     `ToSeasonCode` set to the season (the `SeasonCode` parameter is dropped);
  2. only when every played game of the season is in a single phase (today: all
     `RS`), the `all` feed is also requested for that phase, because the two
     scopes are then the same data.
- The manifest row of a stored fallback answer carries the parameters that were
  actually used, so bronze shows where each version came from. Sort parameters
  are never changed.

**4. Reporting.** A feed whose stored or kept version is still not complete
after all of this is listed as "behind v2" (new `behind_resources` in the fetch
summary beside `kept_resources`; a `[behind]` line per feed; a count and the
names in the pipeline's Refresh summary). It is a warning only: not a failed
request, no change to the exit code, Silver, Gold or publish rules.

**5. Multi-club codes and comments.** `stats_feed_size` stops counting codes
with `;` as clubs. Correct the comment in `fetch_to_cache` and the README line
that call the cache "2 hour CDN": the staleness is per query key upstream.

**Must not break:**
- feeds that grow normally, completed seasons (never fetched again), standings
  and every other resource;
- the kept-version rule and the existing tests of F-01 (the `[kept]` line and
  `kept_resources` now cover a stored copy that is worse or behind, see Step 3);
- the working tree holds unrelated uncommitted Win Shares per 40 changes: keep
  them out of this fix's commits.

## Build steps

- [x] **Step 1 - Completeness check and reporting** - add the per-scope expected
  games from v2, the `complete` test, the coverage rule for storing incomplete
  answers, `STALE_RETRIES = 4`, the `;` rule in `stats_feed_size`, `behind_resources`
  through `api_requests/main.py` and `pipeline.py`, and the comment and README
  corrections. Tests with the fake client in `api_requests/tests/test_scrapper.py`
  and `neon_publish/tests/test_publish.py`:
  - a stale answer that is not worse (accumulated and `perGame`, team and player
    feeds) is retried, then listed as behind v2 and not stored over a better
    stored version;
  - a complete answer is stored and not listed;
  - an incomplete answer with more club-games than stored is stored and listed;
  - `BAS;TEL` neither counts as a club nor fails the check;
  - the pipeline summary lists behind feeds only when there are any.

  *Done when:* `cd api_requests && python -m unittest tests.test_scrapper` and
  the publish tests pass.
- [x] **Step 2 - Fallback keys** - build the `Range` and single-phase variants
  and request them after the retries, storing the first complete answer with
  its real parameters in the manifest. Tests: a variant answer that is complete
  replaces a stale canonical one; an incomplete variant is ignored; `all` uses
  the `RS` request only when every played game is `RS`; sort parameters are
  unchanged; at most one request per variant.

  *Done when:* the same test commands pass.

- [x] **Step 3 - Follow-ups from the live run** (owner: "fix everything",
  2026-10-03). The live refresh showed 28 stale main keys retried 5 times each
  (about 6 of 7 minutes) while every stored copy was already complete, and a
  `[kept]` list of 28 feeds with nothing wrong:
  - a stored copy that is complete against the v2 games gets no retries (one
    request per feed): a stale answer cannot improve it, and a complete one
    (for example a stat correction) is still stored when it arrives;
  - when the stored copy is complete, a stale answer is still recorded in the
    manifest, but the run prints `[current]` instead of `[kept]` and the feed is
    not added to `kept_resources`; `[kept]` stays for a stored copy that is
    worse or behind;
  - `stats_coverage` returns whole club-games (messages show `12`, not `12.0`).

  Tests: no retries when the stored copy is complete, retries as before when it
  is behind; `[current]` is printed and `kept_resources` stays empty for a
  complete stored copy while a stale answer for an incomplete one is still
  listed; coverage is an `int`.

  *Done when:* the four test commands pass; update the README paragraph.

## Verify

- All four test commands in `AGENTS.md` pass.
- With the owner's yes (it makes up to about 190 API requests), run
  `python api_requests/main.py -sc 2026 -ds season_stats --refresh-current`.
  Expected: feeds the API answers fresh under any listed key are stored; any
  other feed is listed as behind v2. Compare a stored fallback answer with the
  canonical key's bytes once the canonical key is fresh; they should match.
- `python postgres_etl/main.py -sc 2026 --quality-only` shows no new warning
  and `BAS;TEL` loads as before.
- Neon is not published here; the next normal refresh publishes.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":9386,"specSha256":"f88017245b4aba8d1d2746d7f4ed94cbd1b0b6c39cd139a8d8aca5852ac573ba","branch":"refs/heads/fix/detect-stale-stats-feeds-against-v2-games-and-try-fallback-keys","head":"80fdac9b57872f033b4f5f198e994bf7db6efb67","baseRef":"refs/heads/main","baseCommit":"80fdac9b57872f033b4f5f198e994bf7db6efb67","sourceTree":"479d5fbe7552d7f66b85c0b63bf6a0854257b2ca","absentOptional":[]} -->
