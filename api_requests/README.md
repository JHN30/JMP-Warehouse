# API extraction (`api_requests`)

The fetcher downloads EuroLeague and EuroCup API responses and stores the exact bytes in the **Bronze** layer under `data/bronze/` (see [common/bronze.py](../common/bronze.py)). It is the first stage of the pipeline; the [Silver loader](../postgres_etl/README.md) reads what it stores.

For the structure of each stored response and how it maps to Silver, see the [Bronze catalog](../docs/BRONZE_CATALOG.md). For the resulting tables, see the [Silver catalog](../docs/SILVER_CATALOG.md).

## Contents

- [Data sources](#data-sources)
- [Running the fetcher](#running-the-fetcher)
- [Datasets](#datasets)
- [Refreshing the current season](#refreshing-the-current-season)
- [Stale statistics feeds](#stale-statistics-feeds)
- [Rate limiting, failures and output](#rate-limiting-failures-and-output)
- [Bronze layout](#bronze-layout)
- [Endpoints checked and not downloaded](#endpoints-checked-and-not-downloaded)
- [Change log](#change-log)

## Data sources

The fetcher uses three APIs. The v2 and v3 APIs are the primary sources. The live API is used only for the two things v2 and v3 lack: play-by-play and shot coordinates.

| API | Host | Seasons | Used for |
| --- | --- | --- | --- |
| **v2** | `https://api-live.euroleague.net` | 2000 onward | Seasons, fixtures, clubs, people, rounds, per-game box scores |
| **v3** | `https://api-live.euroleague.net` | 2000 onward | Player and team season statistics, round standings |
| **live** | `https://live.euroleague.net/api` | 2007 onward | Play-by-play and shot attempts |

v2 and v3 coverage from 2000 was checked on E2000, E2007 and E2015. The live API has no data before E2007.

The live API's `Boxscore`, `Evolution`, `Comparison`, `ShootingGraphic` and `Header` endpoints are not requested. A comparison over all 402 E2025 games showed that each one repeats or can be calculated from data already downloaded:

- `Boxscore` duplicates the v2 game stats; quarter scores, attendance and referees are in the v2 game list.
- `ShootingGraphic` can be summed from the shots.
- `Evolution` can be rebuilt from play-by-play.
- `Comparison` can be calculated from v2 box scores and play-by-play.
- `Header` is replaced by the v2 game list.

## Running the fetcher

Run from the repository root. Bronze files always go to the repository's `data/bronze/`, and each run writes a log to `logs/api_requests/`.

```powershell
# Smoke test: one request that caches the 2026-27 fixture list, including future games
python api_requests/main.py -sc 2026 -ds game_lists

# Every dataset for the 2026-27 EuroLeague season
python api_requests/main.py -sc 2026

# One EuroCup season
python api_requests/main.py -cp eurocup -sc 2025

# Selected datasets only
python api_requests/main.py -sc 2025 -ds game_lists game_stats play_by_play shooting_charts

# Full history (resumable: a rerun skips everything already stored)
python api_requests/main.py -sc 2000-2026
python api_requests/main.py -cp eurocup -sc 2000-2026
```

You can stop a long run with Ctrl+C. Every response and manifest entry is written as soon as it arrives, so rerunning the same command continues where it stopped.

### Options

| Option | Default | Meaning |
| --- | --- | --- |
| `-cp`, `--competition` | `euroleague` | `euroleague` or `eurocup`. |
| `-sc`, `--season_code` | current season | Start years or inclusive ranges, for example `2025` or `2000-2026`. Full codes such as `E2025` are not accepted here. The current season is the current year from September to December, otherwise the previous year. |
| `-ds`, `--dataset` | `all` | One or more [datasets](#datasets). |
| `--refresh-current` | off | Re-fetch every changing current-season resource, including every standings round. |
| `--hot-hours` | `48` | How long after a game its season data is re-fetched. See [Refreshing](#refreshing-the-current-season). |
| `--request-interval` | `2.5` | Minimum seconds between requests. Change it only if you understand the upstream limit. |
| `-gcs`, `--game_code_start` | `1` | Start game-level work at this game code, for the first requested season only. Future fixtures are still cached. |
| `-fel`, `--failed_extractions_limit` | `500` | Warning threshold for failed requests. Failures never stop a season. |
| `--summary-file` | none | Writes the changed resources and failed-request count as JSON. `pipeline.py` uses it to skip loading when nothing changed. |

## Datasets

`all` selects every dataset below. In the endpoint paths, `{c}` is the competition code (`E` EuroLeague, `U` EuroCup), `{s}` the season code (`E2025` is 2025-26), `{g}` a game code and `{r}` a round. Bronze paths are relative to `data/bronze/<competition>/<season>/`.

### Summary

| Dataset | Contents | Seasons | Loaded into Silver |
| --- | --- | --- | --- |
| `seasons` | Every season: name, dates, champion | all | `seasons` |
| `game_lists` | Every fixture, played or scheduled, with phase, round, date, clubs, score, quarter scores, venue, attendance and referees | 2000+ | `games`, `game_officials`, `game_period_scores` |
| `clubs` | The season's clubs: names, TV code, crest, country, address, website, venue | 2000+ | `clubs` |
| `season_people` | Every registered player, coach, staff member and official, with profile and club/role registration | 2000+ | `people`, `registrations` |
| `rounds` | Phase, number, name, first and last game date | 2000+ | `rounds` |
| `standings` | Standings after each group-phase round: position, record, form, streaks, home/away, margins | 2000+ | the 7 `standings_*` tables |
| `season_stats` | Player and team season statistics for `all` phases and each played phase | 2000+ | `season_player_stats_*`, `season_team_stats_*` |
| `game_stats` | Box score per played game: player lines, team rows, coach, starters, plus/minus | 2000+ | `game_player_stats`, `game_team_stats`, `game_stat_gaps` |
| `play_by_play` | Every event by quarter: type, clock, player, club, running score | 2007+ | `play_by_play` |
| `shooting_charts` | Every shot attempt with coordinates, zone and fast-break, second-chance and points-off-turnover flags | 2007+ | `shots` |

### Endpoints and Bronze paths

| Dataset | Endpoint | Bronze path |
| --- | --- | --- |
| `seasons` | `GET /v2/competitions/{c}/seasons` | `_catalog/v2/seasons` (shared by all seasons) |
| `game_lists` | `GET /v2/competitions/{c}/seasons/{s}/games` | `v2/games` |
| `clubs` | `GET /v2/competitions/{c}/seasons/{s}/clubs` | `v2/clubs` |
| `season_people` | `GET /v2/competitions/{c}/seasons/{s}/people?offset=&limit=1000` | `v2/season_people_pages/offset_NNNNNN` |
| `rounds` | `GET /v2/competitions/{c}/seasons/{s}/rounds` | `v2/rounds` |
| `standings` | `GET /v3/competitions/{c}/seasons/{s}/rounds/{r}/{feed}` | `v3/standings/{phase}_{round}_{feed}` |
| `season_stats` (players) | `GET /v3/competitions/{c}/statistics/players/{type}` | `v3/season_stats/players_{type}_{phase}_{mode}` |
| `season_stats` (teams) | `GET /v3/competitions/{c}/statistics/teams/{type}` | `v3/season_stats/teams_{type}_{phase}_accumulated` |
| `game_stats` | `GET /v2/competitions/{c}/seasons/{s}/games/{g}/stats` | `v2/game_stats/{g}` |
| `play_by_play` | live `GET /api/PlayByPlay?gamecode={g}&seasoncode={s}` | `live/{g}/play_by_play` |
| `shooting_charts` | live `GET /api/Points?gamecode={g}&seasoncode={s}` | `live/{g}/shooting_charts` |

### Dataset notes

**`season_people`** may return only its first 500 rows while reporting a larger `total`. The fetcher requests every `offset` page, stores each page as received, and checks that the pages together hold `total` rows. Incomplete pages are fetched again. The Silver loader combines the pages.

**`standings`** has five feeds per round: `basicstandings`, `calendarstandings`, `streaks`, `aheadbehind` and `margins`. The feeds do not cover knockout rounds, so the fetcher requests them only for played rounds where the v2 game list's `phaseType.isGroupPhase` is true. This avoids expected 404 responses for playoffs and the Final Four.

**`season_stats`** requests these feeds:

| Feed | Types | Modes | Parameters |
| --- | --- | --- | --- |
| Players | `traditional`, `advanced`, `scoring`, `misc` | `accumulated`, `perGame` | `SeasonMode=Single`, `SeasonCode`, `StatisticMode`, `Statistic` (sort), `Limit=1000`, optional `PhaseTypeCode` |
| Teams | `traditional`, `advanced` | `accumulated` only | The same, without `Statistic` (the team endpoints reject it) |

`teams/scoring` and `teams/misc` do not exist (404).

**Per-game datasets** (`game_stats`, `play_by_play`, `shooting_charts`) are requested only for played games. A scheduled game stays in `v2/games` but gets no detail until it is marked played. Once stored, a played game's detail is never requested again: this protects the shared rate limit and keeps the response originally received.

## Refreshing the current season

Completed seasons are fetched once. The current season changes, so each run decides what to fetch again:

| Resource | When it is re-fetched |
| --- | --- |
| Game list | Every run, so new fixtures, postponements and results are noticed. |
| Standings of a round | While a game in that round is hot. |
| Season statistics (`all` and each hot phase) | While any game is hot. |
| Clubs, rounds, season people | While any game is hot, and at least every 20 hours otherwise (signings and pre-season changes happen without games). The last check is recorded in `refresh_state.json`. |
| Per-game detail | Never: it is immutable once stored. |
| Season list | Only with `--refresh-current`. |

A current-season game is **hot** when it became played since the previous stored game list, or when it started within the last `--hot-hours` (default 48). Standings and statistics can lag behind the final whistle, so this window keeps a round fresh for two days instead of freezing it at its first fetch. Completed seasons are never hot.

To force a re-fetch of every changing current-season resource, including every standings round:

```powershell
python api_requests/main.py -sc 2026 --refresh-current
```

Every run reports how many stored resources were new or changed.

## Stale statistics feeds

On game days, the v3 statistics and standings endpoints sometimes answer with an older, shorter list, or with nothing. The fetcher detects this and keeps the better stored version.

### Why it happens

The API origin keeps one snapshot per query key, across several upstream instances, and some keys stay frozen for days. For example, the E2026 `RS` player keys stayed at the state after the first 7 games. Cloudflare in front caches answers for at most 60 seconds.

Every statistics request carries an unused `_=<timestamp>` parameter. It bypasses Cloudflare but not the origin, and it is not written to the manifest. Other headers or `Limit` values make no difference.

### How an answer is judged

An answer is **complete** when every club that played in the scope (`all` or one phase) is present with its played games, counted against the v2 game list:

- Team feeds use the club's `gamesPlayed`.
- Player feeds use the highest `gamesPlayed` among the club's players.
- Multi-club codes such as `BAS;TEL` (a player who changed clubs) are ignored.

An answer is **worse** than the stored version when a stored `accumulated` feed would lose clubs or total games, or a stored `perGame` feed would become empty. Per-game feeds list only players with more than half of the phase's games, so they may legitimately shrink.

### What the fetcher does

1. If the answer is worse or incomplete, it asks again up to 4 times (`STALE_RETRIES`) and prints `[stale]` lines. The first good answer is stored. If the stored version is already complete, it asks only once: a stale answer cannot improve it, and a stat correction still arrives as a complete answer.
2. If the answer is still incomplete and so is the stored version, it asks once under each fallback key and stores the first complete answer under the usual name. The parameters actually used are recorded in `manifest.jsonl`. The fallback keys are:
   - `SeasonMode=Range` with `FromSeasonCode` and `ToSeasonCode` set to the season. The sort parameters stay, because they decide `playerRanking` and the row order.
   - While every played game is in one phase (so far `RS`), the `all` feed is also asked for that phase, because both scopes are then the same data.
3. If nothing complete arrives, the answer is stored only if it is not worse and covers at least as many club-games as the stored version. Otherwise the stored version stays in use.

A rejected answer is recorded in `manifest.jsonl` with `stored_as: null` and a `rejected` reason. Every other feed in the run updates normally, and a later refresh stores the complete answer as soon as the API returns it.

### Output

| Marker | Meaning | Listed in the summary file |
| --- | --- | --- |
| `[current]` | The stored version is complete; the API is stale. Nothing to do. | No |
| `[kept]` | The API answer was worse; the stored, incomplete version was kept. | `kept_resources` |
| `[behind]` | The stored version covers fewer club-games than the v2 games. A warning, not a failure. | `behind_resources` |

```text
[current] v3/season_stats/teams_traditional_RS_perGame: stored version is complete against the v2 games; API answered stale (API covers 40 of 60 club-games played)
[kept]    v3/season_stats/teams_traditional_all_accumulated: API answered 0 clubs / 0 games, stored version has 20 / 36 in all 5 attempt(s); kept the stored version, refresh again later
[behind]  v3/season_stats/teams_traditional_RS_accumulated: stored version covers 48 of 60 club-games of the v2 games, refresh again later
```

The run summary counts them as "Stats feeds kept from an earlier fetch" and "Stats feeds behind the v2 games".

## Rate limiting, failures and output

All requests across the three APIs share one client with a minimum interval of 2.5 seconds. HTTP 429 responses honour the server's `Retry-After` value. Transient network errors and 5xx responses are retried twice.

Failures are appended to `failures.jsonl` and to the manifest, with the HTTP status when there is one. They never end a season; `-fel` only sets the warning threshold.

An HTTP 200 response with an empty payload is still stored. In particular, an empty `Points.Rows` response is kept and reported, because a success status does not prove that shot data exists.

The terminal shows every cache decision:

| Marker | Meaning |
| --- | --- |
| `[request]` | A request is about to be sent (printed before any rate-limit wait). |
| `[saved]` | The response differs from the latest stored version and was stored. |
| `[same]` | The response is identical to the latest stored version; nothing was written. |
| `[cached]` | A stored response was reused without a request. |

Before a played game's detail is processed, a progress line shows the season, phase, round, game code and elapsed time, once per game. Progress, warning, failure and summary lines show two timers: `TimeCounter` (the current season) and `TotalTime` (the whole run).

## Bronze layout

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
        ├── v2/clubs/…  v2/rounds/…  v2/season_people_pages/offset_000000/…
        ├── v2/game_stats/<game-code>/…
        ├── v3/season_stats/players_<category>_<phase>_<mode>/…
        ├── v3/standings/<phase>_<round>_<feed>/…
        └── live/<game-code>/{play_by_play,shooting_charts}/…
```

Each resource folder holds one gzipped file per **distinct** response, containing the exact bytes received. An identical response writes nothing; a changed response adds a new version instead of overwriting. Readers use the newest file. The [Bronze catalog](../docs/BRONZE_CATALOG.md) describes the manifest and version identity in detail.

The pre-Bronze cache in `old/data/` is no longer read.

## Endpoints checked and not downloaded

Surveyed on 2026-09-27. The API's Swagger pages list no paths, so these endpoints were found by probing. Each one repeats downloaded data or can be calculated from it.

| Endpoint | Why it is not downloaded |
| --- | --- |
| v3 `statistics/players/leaders`, `statistics/teams/leaders` | Rankings of the season statistics feeds |
| v2 and v3 `seasons/{s}/clubs/{club}/stats` | One club's season totals: sums of the v2 box scores, and in the team statistics feeds |
| v2 `seasons/{s}/people/{p}/stats` | One player's game log: the same rows as the v2 box scores |
| v2 `seasons/{s}/games/{g}/teamsComparison` | Pre-game offense and defense ranks, calculated from earlier box scores |
| v3 `seasons/{s}/games/{g}/stats` | The same fields as v2 `games/{g}/stats` |
| v2 `seasons/{s}`, `games/{g}`, `rounds/{r}`, `clubs/{club}`, `people/{p}` | One row of a downloaded list, with the same fields |
| v2 `venues`, `venues/{code}`, `seasons/{s}/venues` | Venue name, capacity, address and image, already in every v2 game |
| v2 `clubs`, `clubs/{club}` (catalogue) | The season clubs hold the same details; only fax and some social links are extra |
| v2 `people/{p}` (catalogue) | Identical to the `person` object in the season people pages |
| v2 `seasons/{s}/phases` | Phase dates and order, calculated from rounds and games |
| v2 `competitions`, `competitions/{c}` | Competition names only |
| live `Header` | Stadium, coaches, fouls, timeouts and referees: in v2 games, box scores and play-by-play; empty before E2007 |
| v1 `results`, `schedules`, `standings`, `teams`, `players`, `games` | The same data in the old XML format |

## Change log

### 2026-10-25: unused downloads dropped

- Removed the optional live datasets `live_boxscores`, `live_evolution`, `live_comparison` and `live_scoring`, and the `-api` option. None had ever been downloaded.
- The team opponents statistics feeds and the team per-game mode are no longer fetched.
- `rosters` (`v2/rosters/{club}`) is no longer fetched or loaded. In every season E2000-E2026, each roster entry was already in the season people pages with identical values. Existing roster versions stay in the archive.

### 2026-09-24: Bronze layer and endpoint trim (M2)

- Responses are stored as exact bytes, gzipped and versioned in `data/bronze/`, with a JSONL manifest.
- Boxscore, Evolution, Comparison and ShootingGraphic are no longer fetched by default (7 → 3 requests per played game).
- Season-people pages are kept as received; the synthetic combined file is gone.
- Current-season clubs, rounds, people and rosters are re-checked at least every 20 hours.

### 2026-09-24: automatic current-season refresh

- Standings, v3 statistics, clubs, rounds, people and rosters refresh automatically after hot current-season games (`--hot-hours`).
- Changed resources are tracked per run and optionally written with `--summary-file`.

### 2026-09-13: primary API cache refactor

- Replaced Final Four and failure-count season termination with the v2 game list.
- Cached all future fixtures through v2 while limiting per-game detail to played games.
- Added v2 clubs, per-club rosters, season people, rounds and game statistics, v3 season statistics and five round-standing feeds.
- Removed bulk live `Header` calls, because the v2 game lists provide the same metadata.
- Added a shared rate limiter, retries, `Retry-After` handling, raw manifests and JSONL failure logs.
- Added offset pagination and completeness checks for v2 season people.
- Fixed the `PlayByPlay` endpoint-name mismatch that silently skipped play-by-play files.
