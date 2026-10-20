# API extraction cache

See the [EuroLeague Bronze catalog](../docs/BRONZE_CATALOG.md) for response
containers, version identity, manifest fields and lineage into Silver, and the
[Silver catalog](../docs/SILVER_CATALOG.md) for the resulting tables.

This tool stores the exact API responses from the EuroLeague and EuroCup APIs in
the **bronze** layer (`data/bronze/`, see [common/bronze.py](../common/bronze.py)). It uses v2
and v3 as the primary sources, then adds the only data the live API has
that v2/v3 lack: play-by-play and shot coordinates.

## Source policy

| Data                                                                      | Primary source  | Cache policy                                                         |
| ------------------------------------------------------------------------- | --------------- | -------------------------------------------------------------------- |
| Season catalogue, fixtures, clubs, people, rosters and rounds             | v2              | Cache all fixtures, including future games                           |
| Per-game player/team statistics                                           | v2              | Fetch only after a game is played                                    |
| Season people                                                             | v2              | Fetch every offset page, including coaches, officials and staff      |
| Season player statistics and round standings                              | v3              | Fetch for played phases; standings are limited to group-phase rounds |
| Play-by-play and shot coordinates                                         | live API        | Fetch only after a game is played and only from season 2007 onward   |
| Boxscore, Evolution, Comparison, ShootingGraphic (optional)               | live API        | Not fetched by default: covered by v2, play-by-play or shots         |

v2/v3 cover every season from E2000 (checked on E2000, E2007 and E2015). The live
API has no data before E2007. Comparing all 402 E2025 games showed that Boxscore
duplicates v2 game stats (quarters, attendance and referees are in the v2 game
list), ShootingGraphic can be summed from shots, Evolution from play-by-play, and
Comparison from v2 box scores and play-by-play. They can still be requested by
name with `-ds`.

The v2 game list replaces the live API's Header endpoint for bulk extraction. A
future scheduled game is retained in v2/games.json, but its per-game stats and
live detail are intentionally not requested until it is marked played.

The v2 season-people endpoint may return only its first 500 rows while
reporting a larger total. The extractor requests every `offset` page, keeps the
page response in `v2/season_people_pages/offset_NNNNNN`, and checks that the
pages together hold `total` rows. Incomplete pages are fetched again. The loader
combines the pages.

The standings feeds do not cover knockout rounds. The extractor uses the v2
game-list field phaseType.isGroupPhase and requests standings only for played
group-phase rounds, avoiding expected playoff and Final Four 404 responses.

## Default datasets

The default all dataset selection caches:

- seasons
- game_lists
- clubs
- rosters
- rounds
- season_people
- season_stats
- standings
- game_stats
- play_by_play
- shooting_charts

Optional, only when named with `-ds`: live_boxscores, live_evolution,
live_comparison, live_scoring. They are archived in bronze only; the loader
does not read them, since v2 game data, play-by-play and shots cover their
content.

The live dataset names map to live API endpoints:

- shooting_charts uses Points, which provides shot attempts and coordinates.
- live_scoring uses ShootingGraphic, which contains scoring-context summaries.

## Endpoint reference

Every endpoint the extractor downloads. `{c}` is the competition code (`E`
EuroLeague, `U` EuroCup), `{s}` the season code (`E2025` = 2025-26), `{g}` a
game code. v2/v3 are served by `https://api-live.euroleague.net`, the live API
by `https://live.euroleague.net/api`. Bronze paths are relative to
`data/bronze/<competition>/<season>/` (`_catalog/` for the season list).
"Hot" is defined under [Refreshing](#refreshing). Loaded tables are the local
PostgreSQL names (see [docs/DATA_DICTIONARY.md](../docs/DATA_DICTIONARY.md)).

| `-ds` | Endpoint | Bronze resource | Contents | Seasons | Fetched | Loaded into |
| --- | --- | --- | --- | --- | --- | --- |
| seasons | `GET /v2/competitions/{c}/seasons` | `_catalog/v2/seasons` | Every season: name, dates, champion | all | Once; again with `--refresh-current` | `seasons` |
| game_lists | `GET /v2/competitions/{c}/seasons/{s}/games` | `v2/games` | Every fixture, played or scheduled: phase, round, date, clubs, score, quarter scores, venue (with capacity and address), attendance, referees | E2000+ | Current season every run; completed seasons once | `games`, `game_officials`, `game_period_scores` |
| clubs | `GET /v2/competitions/{c}/seasons/{s}/clubs` | `v2/clubs` | The season's clubs: names, TV code, crest, country, address, city, website, venue | E2000+ | Current season while hot and at least every 20 h; completed once | `clubs` |
| season_people | `GET /v2/competitions/{c}/seasons/{s}/people?offset=&limit=1000` | `v2/season_people_pages/offset_NNNNNN` | Every person registered that season (players, coaches, staff, officials): profile (height, weight, birth date and country) and club/role registration | E2000+ | Like clubs; all pages each time | `people`, `registrations` |
| rosters | `GET /v2/competitions/{c}/seasons/{s}/clubs/{club}/people` (per club) | `v2/rosters/{club}` | One club's registrations: dorsal, position, start and end dates | E2000+ | Like clubs | `people`, `registrations` |
| rounds | `GET /v2/competitions/{c}/seasons/{s}/rounds` | `v2/rounds` | Rounds: phase, number, name, first and last game date | E2000+ | Like clubs | `rounds` |
| standings | `GET /v3/competitions/{c}/seasons/{s}/rounds/{r}/{feed}`, feed = `basicstandings`, `calendarstandings`, `streaks`, `aheadbehind`, `margins` (per played group-phase round) | `v3/standings/{phase}_{round}_{feed}` | Standings after that round: position, record, points for/against, form, streaks, home/away, ahead/behind at checkpoints, margin bands | E2000+, group phases only | Once per round; hot rounds again; all with `--refresh-current` | 7 `standings_*` silver tables |
| season_stats | `GET /v3/competitions/{c}/statistics/players/{type}`, type = `traditional`, `advanced`, `scoring`, `misc`; params `SeasonMode=Single`, `SeasonCode`, `StatisticMode` (`accumulated`, `perGame`), `Statistic` (sort), `Limit=1000`, optional `PhaseTypeCode` | `v3/season_stats/players_{type}_{phase}_{mode}` | Player season statistics for `all` phases and each played phase, totals and per game | E2000+ | Once; `all` and hot phases again while a game is hot; all with `--refresh-current` | `season_player_stats_*` |
| season_stats | `GET /v3/competitions/{c}/statistics/teams/{type}`, type = `traditional`, `advanced`, `opponentsTraditional`, `opponentsAdvanced`; same params without `Statistic` (the team endpoints reject it) | `v3/season_stats/teams_{feed}_{phase}_{mode}` (`opponentsTraditional` is stored as `opponents_traditional`) | Team season statistics, and what each team's opponents did against it, for `all` and each played phase, totals and per game | E2000+ | Like the player feeds | `season_team_stats_*` |
| game_stats | `GET /v2/competitions/{c}/seasons/{s}/games/{g}/stats` (per played game) | `v2/game_stats/{g}` | Box score: every player's line, the team row and totals, coach, starters, plus/minus | E2000+ | Once per played game | `game_player_stats`, `game_team_stats`, `game_stat_gaps` |
| play_by_play | `GET /api/PlayByPlay?gamecode={g}&seasoncode={s}` (live API) | `live/{g}/play_by_play` | Every event by quarter: type, clock, player, club, running score | E2007+ | Once per played game | `play_by_play` |
| shooting_charts | `GET /api/Points?gamecode={g}&seasoncode={s}` (live API) | `live/{g}/shooting_charts` | Every shot attempt, made or missed: coordinates, zone, fast-break, second-chance and points-off-turnover flags | E2007+ | Once per played game | `shots` |
| live_boxscores, live_evolution, live_comparison, live_scoring (optional) | `GET /api/{Boxscore,Evolution,Comparison,ShootingGraphic}?gamecode={g}&seasoncode={s}` (live API) | `live/{g}/{dataset}` | Live box score, minute-by-minute score, starters/bench comparison, fast-break/second-chance/turnover points | E2007+ | Only when named with `-ds` | Not loaded (bronze only) |

## Checked, not downloaded

Surveyed on 2026-09-27. The API's Swagger pages list no paths, so these were
found by probing. Each one repeats downloaded data or can be calculated from it:

| Endpoint | Why it is not downloaded |
| --- | --- |
| v3 `statistics/players/leaders`, `statistics/teams/leaders` | Rankings of the player and team season statistics |
| v2 and v3 `seasons/{s}/clubs/{club}/stats` | One club's season totals and averages: sums of the v2 game box scores, and in the team statistics feeds |
| v2 `seasons/{s}/people/{p}/stats` | One player's game log: the same rows as the v2 game box scores |
| v2 `seasons/{s}/games/{g}/teamsComparison` | Pre-game offense and defense ranks, calculated from box scores up to that game |
| v3 `seasons/{s}/games/{g}/stats` | The same fields as v2 `games/{g}/stats` |
| v2 single items: `seasons/{s}`, `games/{g}`, `rounds/{r}`, `clubs/{club}`, `people/{p}` | One row of a downloaded list, same fields |
| v2 `venues`, `venues/{code}`, `seasons/{s}/venues` | Venue name, capacity, address and image, already inside every v2 game |
| v2 `clubs`, `clubs/{club}` (catalogue) | The season clubs hold the same details; only fax and some social links are extra |
| v2 `people/{p}` (catalogue) | Identical to the `person` object in the season people pages |
| v2 `seasons/{s}/phases` | Phase start and end dates and order, calculated from rounds and games |
| v2 `competitions`, `competitions/{c}` | Competition names only |
| live API `Header` | Game header (stadium, coaches, fouls, timeouts, referees): in v2 games, box scores and play-by-play; empty before E2007 |
| v1 `results`, `schedules`, `standings`, `teams`, `players`, `games` | The same data in the old XML format |

`teams/scoring` and `teams/misc` do not exist (404).

## Running it

Run commands from this folder:

```powershell
cd api_requests
```

Start with a safe smoke test. It makes one request and caches the 2026-27
fixture list, including future games:

```powershell
python main.py -sc 2026 -ds game_lists
```

Fetch every supported dataset for the current EuroLeague season:

```powershell
python main.py -sc 2026
```

Fetch both competitions for a specific season:

```powershell
python main.py -cp eurocup -sc 2025
```

Request only selected data:

```powershell
python main.py -sc 2025 -ds game_lists game_stats play_by_play shooting_charts
```

Use -api only to restrict the live API requests:

```powershell
python main.py -sc 2025 -ds game_lists live_boxscores play_by_play -api Boxscore PlayByPlay
```

`PlayByPlay` is the canonical endpoint spelling. The previous `PlaybyPlay`
spelling is accepted as a command-line alias for compatibility.

## Refreshing

The game list for the current season is refreshed on every run so new fixtures,
postponements and game status changes are noticed.

Mutable current-season data refreshes itself. A current-season game is **hot**
when it became played since the previous cached game list, or when it started
within the last `--hot-hours` (default 48). While any game is hot, a run
re-fetches:

- the five standings feeds of each hot group-phase round,
- v3 season statistics for `all` and for each hot phase,
- clubs, rounds, season people and rosters.

Standings and statistics can lag behind the final whistle, so the window keeps a
round fresh for two days instead of freezing it at its first fetch. Completed
seasons are never hot.

Clubs, rounds, season people and rosters also change without games (signings,
pre-season), so for the current season they are re-checked at least every 20
hours even when no game is hot. The last check is recorded in
`refresh_state.json`.

On game days the v3 statistics and standings endpoints answer an older, shorter
list or nothing for some requests. The origin keeps one snapshot per query key
(several upstream instances; some keys stayed frozen for days, for example the
E2026 `RS` player keys at the state after the first 7 games). Cloudflare in
front caches for 60 seconds at most. These requests carry an unused
`_=<timestamp>` parameter, which clears Cloudflare but not the origin, and it is
not written to the manifest. Other headers or `Limit` values change nothing.

A statistics answer must be **complete** against the v2 game list: every club
that played in the scope (`all` or a phase) is present with its played games
(team feeds: the club's `gamesPlayed`; player feeds: the highest `gamesPlayed` of
its players). Multi-club codes such as `BAS;TEL` (a player who changed clubs) are
ignored. An answer is also **worse** when a stored `accumulated` feed would lose
clubs or total games, or a stored `perGame` feed would become empty (per-game
feeds list only players with more than half of the phase's games, so they may
shrink). A feed that is worse or incomplete is asked again up to `STALE_RETRIES`
(4) times (`[stale]` lines) and the first good answer is stored. A stored version
that is already complete is asked only once: a stale answer cannot improve it,
and a complete one (a stat correction) is still stored when it arrives.

If the answer is still incomplete and the stored version is too, the same feed is
asked once under each fallback key and the first complete answer is stored under
the usual name, with the parameters actually used in `manifest.jsonl`:

1. `SeasonMode=Range` with `FromSeasonCode` and `ToSeasonCode` set to the season
   (the sort parameters stay, because they decide `playerRanking` and row order);
2. while every played game is in one phase (so far `RS`), the `all` feed is also
   asked for that phase, because both scopes are then the same data.

When nothing complete arrives, the answer is stored only if it is not worse and
covers at least as many club-games as the stored version (progress is kept);
otherwise the stored version stays in use. If that stored version is complete,
the run prints `[current]` (the API is stale, nothing to do). Otherwise it
prints `[kept]` and the feed is listed. The run prints, for example:

```text
[current] v3/season_stats/teams_traditional_RS_perGame: stored version is complete against the v2 games; API answered stale (API covers 40 of 60 club-games played)
[kept]    v3/season_stats/teams_traditional_all_accumulated: API answered 0 clubs / 0 games, stored version has 20 / 36 in all 5 attempt(s); kept the stored version, refresh again later
[behind]  v3/season_stats/teams_traditional_RS_accumulated: stored version covers 48 of 60 club-games of the v2 games, refresh again later
```

The summary line counts both ("Stats feeds kept from an earlier fetch", "Stats
feeds behind the v2 games"), the `--summary-file` lists them under
`kept_resources` and `behind_resources` (a `[current]` feed is in neither), and
a rejected answer, `[current]` ones included, is recorded in
`manifest.jsonl` with `stored_as: null` and a `rejected` reason. `[behind]` is a
warning, not a failure. Every other feed in the run updates normally. A later
refresh stores the complete answer as soon as the API returns it.

Use --refresh-current to force a re-fetch of all mutable current-season resources,
including every standings round.

```powershell
python main.py -sc 2026 --refresh-current
```

Game-level v2 stats and live API responses are immutable cache entries: once
saved for a played game, they are not requested again. That protects the shared
upstream rate limit and preserves the source response originally received.

Use -gcs to start game-level work from a game code for the first requested
season. It does not exclude future fixtures from the v2 game list.

```powershell
python main.py -sc 2025 -gcs 150
```

To download the full history (resumable: rerunning skips everything stored):

```powershell
python main.py -sc 2000-2026
python main.py -cp eurocup -sc 2000-2026
```

Every run reports how many cached resources were new or changed.
`--summary-file <path>` also writes that list and the failed-request count
as JSON. `pipeline.py` uses it to skip loading when nothing
changed.

## Rate limiting and failures

All requests across v2, v3 and the live host share one client. The default
interval is 2.5 seconds. HTTP 429
responses honor the server's Retry-After value; transient network and 5xx
errors are retried twice.

The terminal reports every cache decision: [request] is printed before any
rate-limit wait, [saved] when a response differs from the latest stored version,
[same] when it is identical (nothing new is written), and [cached] when a
stored response is reused without a request. Every progress, warning, failure and
per-season summary line shows two timers: `TimeCounter` (the current season,
reset for each season) and `TotalTime` (the whole run). The run ends with a
line giving the total time for all seasons.

Before a played game's v2 or live detail is processed, the tool also prints the
traditional progress line with season, phase, round, game code and elapsed
time. Each game is announced once, even though it can have several cached
resources.

Use --request-interval only if you understand the upstream limit:

```powershell
python main.py -sc 2026 --request-interval 6
```

Failures are appended to failures.jsonl and to the manifest (with the HTTP status
when there is one) and do not end a season. The -fel
argument remains a warning threshold.

An HTTP 200 response with an empty payload is still cached. In particular, an
empty Points.Rows response is retained and reported, because success status
does not prove that shot data exists.

You can stop a long run with Ctrl+C. Every completed response and manifest entry
is written immediately, so rerunning the same command continues from bronze
instead of starting the game-level work again.

## Output layout

```text
data/bronze/
└── euroleague/
    ├── _catalog/
    │   └── v2/seasons/<fetched_at>_<sha16>.json.gz
    └── E2026/
        ├── manifest.jsonl          one line per request: url, params, status, sha256, bytes, stored_as
        ├── failures.jsonl
        ├── refresh_state.json
        ├── runs/run_<timestamp>.json
        ├── v2/games/<fetched_at>_<sha16>.json.gz
        ├── v2/clubs/…  v2/rounds/…  v2/rosters/<club>/…  v2/season_people_pages/offset_000000/…
        ├── v2/game_stats/<game-code>/…
        ├── v3/season_stats/players_<category>_<phase>_<mode>/…
        ├── v3/standings/<phase>_<round>_<feed>/…
        └── live/<game-code>/{play_by_play,shooting_charts}/…
```

Each resource folder holds one gzipped file per **distinct** response, containing
the exact bytes received. A refresh that returns identical bytes writes nothing
new, and a changed response adds a version instead of overwriting. Readers use
the newest file. The pre-bronze cache now sits in `old/data/` and is no longer read.

## Change log

### 2026-09-24 - bronze layer and endpoint trim (M2)

- Responses are stored as exact bytes, gzipped and versioned in `data/bronze/`, with a JSONL manifest (url, params, status, sha256, bytes).
- Boxscore, Evolution, Comparison and ShootingGraphic are no longer fetched by default (7 → 3 requests per played game).
- Season-people pages are kept as received; the synthetic combined file is gone.
- Current-season clubs, rounds, people and rosters are re-checked at least every 20 hours.

### 2026-09-24 - automatic current-season refresh

- Standings, v3 statistics, clubs, rounds, people and rosters refresh automatically for hot current-season games (`--hot-hours`).
- Changed resources are tracked per run and optionally written with `--summary-file`.

### 2026-09-13 - primary API cache refactor

- Replaced Final Four and failure-count season termination with the v2 game list.
- Added full future-fixture caching through v2 while limiting per-game detail to played games.
- Added v2 clubs, per-club rosters, season people, rounds and game statistics.
- Added v3 season statistics and five round-standing feeds.
- Added legacy-only play-by-play, shots, live boxscore, evolution, comparison and scoring datasets.
- Removed bulk legacy Header calls because v2 game lists provide the same game metadata.
- Added a shared rate limiter, retries, Retry-After handling, raw manifests and JSONL failure logs.
- Added cache/coverage tests for future games, current-season refreshes and pre-2007 live-data exclusion.
- Added a per-season TimeCounter to cache decisions, progress notices, warnings, failures, rate-limit notices and final reports.
- Fixed the `PlayByPlay` endpoint-name mismatch that silently skipped play-by-play files; the old CLI spelling remains supported.
- Added offset pagination and completeness validation for v2 season people, including automatic upgrades of old partial cache files.
