# EuroLeague Bronze data catalog

Bronze is the file archive of original API response bodies. It supplies the
typed [Silver tables](SILVER_CATALOG.md), which feed the app-facing
[Gold tables](DATA_CATALOG.md). This catalog describes EuroLeague resources
implemented by the repository, checked on 2026-10-20. It does not assert that
every resource exists for every game or that an API response is complete.
EuroCup documentation will be added when that work begins.

Use the [Silver column reference](SILVER_TABLE_REFERENCE.md) for extracted
fields and the shared [player/team stats glossary](STAT_GLOSSARY.md) for metric
definitions. Bronze responses are JSON documents; they do not have fixed SQL
column types, primary keys or Silver's NULL normalization.

## Storage and version identity

```text
data/bronze/euroleague/
  _catalog/
    v2/seasons/<fetched_at>_<sha16>.json.gz
    manifest.jsonl
  E2025/
    v2/games/<fetched_at>_<sha16>.json.gz
    v2/game_stats/31/<fetched_at>_<sha16>.json.gz
    v2/season_people_pages/offset_000000/<fetched_at>_<sha16>.json.gz
    v3/season_stats/players_traditional_RS_accumulated/<fetched_at>_<sha16>.json.gz
    v3/standings/RS_10_basicstandings/<fetched_at>_<sha16>.json.gz
    live/31/play_by_play/<fetched_at>_<sha16>.json.gz
    live/31/shooting_charts/<fetched_at>_<sha16>.json.gz
    manifest.jsonl
    failures.jsonl
    refresh_state.json
    runs/run_<timestamp>.json
```

`E2025` means 2025-26. `_catalog` is the competition-wide scope; all other
resource paths below are relative to a season directory. `<fetched_at>` is a UTC
stamp in `YYYYMMDDTHHMMSSffffffZ` format. `<sha16>` is the first 16 hexadecimal
characters of the SHA-256 of the uncompressed response bytes.

The client passes `response.content` to the store. Decompressing a stored version
recovers those bytes; the JSON is not reformatted or cleaned first. The hash is
byte-based: whitespace or source ordering changes can create a new version even
when the parsed objects are semantically equivalent.

A version is written only when its hash prefix differs from the latest version's
prefix. This is comparison with the latest version, not global deduplication:
an A -> B -> A response sequence can produce three files. Version files are
never overwritten. A temporary file is atomically renamed into place; readers
choose the lexicographically last version filename for each logical resource.

Parser paths such as `v2/games.json` are logical handles inside `RawSeason`.
The actual archive uses `v2/games/<version>.json.gz`; do not search for a single
mutable `games.json` as the stored source of truth.

Implementation: [common/bronze.py](../common/bronze.py),
[api_client.py](../api_requests/api_client.py),
[raw_transform.py](../postgres_etl/raw_transform.py).

## Resource notation and API hosts

| Placeholder | Meaning |
| --- | --- |
| `{s}` | EuroLeague season code, for example E2025. |
| `{g}` | Game code within the season. |
| `{club}` | Club code from the season's clubs/fixtures. |
| `{phase}` | `all` or a phase observed in played fixtures, such as RS, TS, PI, PO or FF. No synthetic PS request. |
| `{mode}` | `accumulated` or `perGame`. |
| `{r}` | Round number from played group-phase fixtures. |
| `offset_NNNNNN` | Zero-padded numeric people-page offset, starting at 000000. |

v2 and v3 endpoints use `https://api-live.euroleague.net` with competition
code `E`. Live endpoints use `https://live.euroleague.net/api`.
The paths are the extractor's implemented API contract, not independently
revalidated live endpoints. The [extractor README](../api_requests/README.md)
contains command and refresh details.

## v2 catalog, profiles, fixtures and box scores

| Resource | Dataset / endpoint | Response container and contents | Silver output |
| --- | --- | --- | --- |
| `_catalog/v2/seasons` | `seasons`: `GET /v2/competitions/E/seasons` | `data[]`: season code, year, names, dates and winner. One response contains the competition season list; Silver selects a season. | [`seasons`](SILVER_TABLE_REFERENCE.md#seasons) |
| `v2/games` | `game_lists`: `GET /v2/competitions/E/seasons/{s}/games` | `data[]`: scheduled and played fixtures, local/road clubs and scores, phase/group/round, dates, venue, attendance, referee1-4 and side partial scores. | [`games`](SILVER_TABLE_REFERENCE.md#games), [`game_officials`](SILVER_TABLE_REFERENCE.md#game_officials), [`game_period_scores`](SILVER_TABLE_REFERENCE.md#game_period_scores) |
| `v2/clubs` | `clubs`: `GET /v2/competitions/E/seasons/{s}/clubs` | `data[]`: club names, codes, crests, country, contact, venue and sponsor details. | [`clubs`](SILVER_TABLE_REFERENCE.md#clubs) |
| `v2/rounds` | `rounds`: `GET /v2/competitions/E/seasons/{s}/rounds` | `data[]`: phase, round, index, source name and first/last game dates. | [`rounds`](SILVER_TABLE_REFERENCE.md#rounds) |
| `v2/season_people_pages/offset_NNNNNN` | `season_people`: `GET /v2/competitions/E/seasons/{s}/people?offset={offset}&limit=1000` | `data[]` plus `total`: registration entries containing person profiles and club/role context. Includes coaches, staff and officials, not only players. | [`people`](SILVER_TABLE_REFERENCE.md#people), [`registrations`](SILVER_TABLE_REFERENCE.md#registrations) |
| `v2/rosters/{club}` (archive only; no longer fetched or loaded) | `rosters`: `GET /v2/competitions/E/seasons/{s}/clubs/{club}/people` | Registration/person entries as `data[]` or a list accepted by the loader. Jersey, position, club, role and registration dates supplement season people. | [`people`](SILVER_TABLE_REFERENCE.md#people), [`registrations`](SILVER_TABLE_REFERENCE.md#registrations) |
| `v2/game_stats/{g}` | `game_stats`: `GET /v2/competitions/E/seasons/{s}/games/{g}/stats` | `local` and `road` objects with `players[]`, `team`, `total`, `coach`. Player entries contain `player` registration/profile context and `stats`. | [`game_player_stats`](SILVER_TABLE_REFERENCE.md#game_player_stats), [`game_team_stats`](SILVER_TABLE_REFERENCE.md#game_team_stats), [`game_stat_gaps`](SILVER_TABLE_REFERENCE.md#game_stat_gaps) |

These sources support E2000 onward subject to actual data. Fixture lists retain
future games. Per-game statistics are requested only for fixtures marked played.
A played forfeit can have an empty player box score; the source remains intact
and Silver records `stat_name = '*'` rather than manufacturing player rows.

People pagination matters: the endpoint can return 500 entries even when asked
for 1000, so the extractor advances by received entries and checks the reported
total. Each page has its own exact response version. The loader combines the pages,
deduplicates people/registrations and ignores page offsets beyond the current
reported total.

Club rosters (`v2/rosters/{club}`) are no longer fetched or loaded. In every season
E2000-E2026 each roster entry was already in the people pages with identical values, and
rosters had no extra fields. Older roster versions remain in the archive.

## v3 player and team season statistics

All six feeds use dataset `season_stats` and resource pattern
`v3/season_stats/{feed}_{phase}_{mode}`. Responses use `players[]` or `teams[]`;
each entry combines profile/team context with category measures. The source
entry order is retained as player `entry_ordinal`; it is not a permanent ID.
Transferred players can have a semicolon-separated team code such as `BAS;TEL`.
That retained source value is not a single club identity for a direct profile join.

| Resource feed | Endpoint after `/v3/competitions/E/statistics/` | Main measures | Silver table |
| --- | --- | --- | --- |
| `players_traditional` | `players/traditional` | Games, minutes, points, shooting, rebounds, assists, steals, turnovers, blocks, fouls and PIR. | [`season_player_stats_traditional`](SILVER_TABLE_REFERENCE.md#season_player_stats_traditional) |
| `players_advanced` | `players/advanced` | API eFG/TS/rebound percentages, assist/turnover ratios, attempt ratios, free-throw rate and possessions. | [`season_player_stats_advanced`](SILVER_TABLE_REFERENCE.md#season_player_stats_advanced) |
| `players_scoring` | `players/scoring` | Shot mix, source shares/rates and points-source percentages. | [`season_player_stats_scoring`](SILVER_TABLE_REFERENCE.md#season_player_stats_scoring) |
| `players_misc` | `players/misc` | Games, starts, wins/losses, minutes, double/triple doubles. | [`season_player_stats_misc`](SILVER_TABLE_REFERENCE.md#season_player_stats_misc) |
| `teams_traditional` | `teams/traditional` | Team traditional totals/averages and shooting percentages. | [`season_team_stats_traditional`](SILVER_TABLE_REFERENCE.md#season_team_stats_traditional) |
| `teams_advanced` | `teams/advanced` | Team API efficiency, rebound, assist/turnover, shooting mix and scoring-source measures. | [`season_team_stats_advanced`](SILVER_TABLE_REFERENCE.md#season_team_stats_advanced) |

Primary query parameters are `SeasonMode=Single`, `SeasonCode={s}`,
`StatisticMode={mode}`, `Limit=1000`, plus `PhaseTypeCode` for a specific phase.
The `all` request omits that phase filter. Player queries use `Statistic=timePlayed`
for traditional/advanced and `gamesPlayed` for scoring/misc, with descending sort
and `StatisticSortMode={mode}`. Team queries omit those three player sort keys.

The extractor requests all phases and each phase present in played fixtures
after the season has played games: the player feeds in both modes, the team feeds
in accumulated mode only (their only reader is Gold's accumulated API cross-check).
The opponents feeds (`teams/opponentsTraditional`, `teams/opponentsAdvanced`) and
team per-game files fetched before 2026-10-25 remain in the archive and are not
loaded; `app_team_season_stats` holds opponent totals from the box scores. The extractor can try equivalent Range
query keys when a source snapshot is stale; the resource identity is unchanged.
The archive retains the response and the request parameters actually used.
There is no independent pagination loop for these v3 statistics feeds: `Limit=1000`
is the configured request. Do not infer upstream completeness from that limit.

The API can omit nonqualifiers from player `perGame`. Bronze and Silver preserve
what it returned. Missing perGame rows, qualification flags and combined postseason
rows are Gold additions. The API team feeds stay local as reference values rather
than being copied to Neon. Their ratio definitions can differ from calculated
Gold measures; see the glossary instead of inferring equivalence from labels.

## v3 official standings

Dataset `standings` uses
`GET /v3/competitions/E/seasons/{s}/rounds/{r}/{feed}`. Each response's `teams[]`
holds club, group, official position and record fields plus feed-specific values.
The archive resource includes phase even though the URL identifies the round.

| Resource | Additional contents | Silver tables | Gold use |
| --- | --- | --- | --- |
| `v3/standings/{phase}_{r}_basicstandings` | Points, home/away/neutral/overtime/last-ten records and `last5Form[]`. | [`standings_basic`](SILVER_TABLE_REFERENCE.md#standings_basic), [`standings_basic_form`](SILVER_TABLE_REFERENCE.md#standings_basic_form) | `app_standings` basic columns and ordered form JSON. |
| `v3/standings/{phase}_{r}_calendarstandings` | Calendar records and `streaks[]` with dates and win-loss text. | [`standings_calendar`](SILVER_TABLE_REFERENCE.md#standings_calendar), [`standings_calendar_streaks`](SILVER_TABLE_REFERENCE.md#standings_calendar_streaks) | `app_standings` calendar columns and streak_history JSON. |
| `v3/standings/{phase}_{r}_streaks` | Current/historical longest streaks and home/away/recent records. | [`standings_streaks`](SILVER_TABLE_REFERENCE.md#standings_streaks) | `app_standings` streaks columns. |
| `v3/standings/{phase}_{r}_aheadbehind` | Result records when ahead/behind/tied after quarter 1, half-time and quarter 3. | [`standings_ahead_behind`](SILVER_TABLE_REFERENCE.md#standings_ahead_behind) | `app_standings` ahead_behind columns. |
| `v3/standings/{phase}_{r}_margins` | Result records by final margin and statistical comparison. | [`standings_margins`](SILVER_TABLE_REFERENCE.md#standings_margins) | `app_standings` margins columns. |

Only played **group-phase** rounds are requested, based on
`phaseType.isGroupPhase` in fixtures. Knockout phases do not acquire empty
standings by design. Source standings snapshots are distinct from calculated
team-round totals; historical round alignment can differ.

## Live events and shots

Live requests use `gamecode={g}&seasoncode={s}` and run only for played games
from E2007 onward. Endpoint spelling and response field casing are preserved.

| Resource | Dataset / endpoint after `/api/` | Response structure and purpose | Silver output |
| --- | --- | --- | --- |
| `live/{g}/play_by_play` | `play_by_play`: `PlayByPlay` | Arrays `FirstQuarter`, `SecondQuarter`, `ThirdQuarter`, `ForthQuarter`, `ExtraTime`. Entries include `PLAYTYPE`, `PLAYER_ID`, `CODETEAM`, `NUMBEROFPLAY`, `MINUTE`, `MARKERTIME` and running scores. | [`play_by_play`](SILVER_TABLE_REFERENCE.md#play_by_play) |
| `live/{g}/shooting_charts` | `shooting_charts`: `Points` | `Rows[]`: `ID_ACTION`, `ID_PLAYER`, `TEAM`, `NUM_ANOT`, `POINTS`, coordinates, zone and fast-break/second-chance/turnover flags. | [`shots`](SILVER_TABLE_REFERENCE.md#shots) |

All overtime events share the `ExtraTime` array; the minute marker identifies
the overtime number. Silver preserves the period label as TEXT. Downstream
event processing maps those labels to chronological ranks, then uses overtime
number and event ordinal. `play_number` is not a chronological sort key.

Raw live player IDs sometimes disagree with v2 box scores. Bronze retains the
original; Silver stores raw `player_code`, resolved `person_code` and
`person_code_method`. Resolution uses available box-score identities, club/jersey,
normalized name and lookup fallbacks. Resolved event person_code joins the
box-score person_key; no unconditional prefix-removal rule guarantees a match.

An HTTP 200 with `Rows: []` is a stored successful response with no shots.
Missing clocks, unrecorded flags and unmatched player identities can prevent
some derived measures even when a response exists. The archive does not fill
these gaps or standardize a coordinate system.

### Other live endpoints (not requested)

The live API's `Boxscore`, `Evolution`, `Comparison`, `ShootingGraphic` and `Header`
endpoints repeat v2 game data, play-by-play or shots (checked on every E2025 game) and
are not requested; the extractor has no dataset for them.

## Refresh and source-quality behavior

| Resource group | Implemented cache behavior |
| --- | --- |
| Season catalog | Cached; refreshed with the extractor's refresh-current option. |
| Current-season fixtures | Refetched every run to observe schedule and played-status changes. |
| Clubs, rounds and people | Current-season refresh while a game is hot, at least every 20 hours, or when refresh-current is requested. |
| Standings and season statistics | Cached snapshots; hot rounds/phases are refreshed, as are current-season mutable resources under refresh-current. |
| Played game box scores and live detail | Reused once stored; refresh-current does not force those game resources to refetch. |
| Completed seasons | Existing resources reused; current-season hot rules do not apply. Missing resources can still be fetched. |

A current-season game is hot when newly marked played since the previous game
list or started within the configured window (default 48 hours). Mutable feeds
can lag after the final whistle. The extractor compares v3 answers with stored
values and expected played-game counts, retries stale answers and may try
equivalent query keys. A worse response can be rejected while retaining the
previous version. If there is no previous version, the last stale answer can
still be stored and reported behind the fixtures. Latest stored does not mean
complete or latest fetched response.

## Manifest and operational files

Each scope has `manifest.jsonl`, one JSON object per log entry. Records from
normal stored/unchanged responses have the fields below. Error and rejected
records have related but different shapes; not every field appears on every line.
Cache reuse without a network request does not add a normal response entry.
Not every internal HTTP retry is separately represented in the manifest.

| Field | Meaning |
| --- | --- |
| `resource` | Logical path within the scope, such as `v2/game_stats/31`. |
| `url` | Request/final URL recorded by that path; normal success uses the response URL. |
| `params` | Request parameters recorded by the extractor. The cache-busting `_` query key can be present in final URL without appearing in this object. |
| `status_code` | HTTP status when available; errors without an HTTP response can have NULL. |
| `fetched_at_utc` | UTC timestamp for the store/log action, not scheduled game time. |
| `sha256` | Full digest of response bytes for successful or rejected JSON answers. |
| `bytes` | Uncompressed response byte length. |
| `stored_as` | New version's filename when saved; NULL for unchanged, rejected or failed answers. Not a full relative path. |
| `rejected` | Reason a stale/worse answer was rejected; absent on normal successful entries. |
| `error` | Recorded request/JSON failure detail; successful response fields can be absent. |

`stored_as: null` alone does not mean failure. Inspect status/error/rejected and
the resource's latest stored file. Rejected response bytes are not separately
saved as versions; the manifest retains their hash/length and rejection reason.
Failed/non-JSON responses are logged as failures, not stored as successful JSON.

`failures.jsonl` records failed extractions. `refresh_state.json` holds mutable
season-resource check timing. `runs/run_<timestamp>.json` records a run summary.
These are operational files, not original API payloads or Silver source tables.
Normal requests share a default 2.5-second interval across hosts; network/5xx
retries and server Retry-After handling are implemented by the API client.

## Read an existing response without fetching

Run this from the repository root. It reads only existing local archive files;
it makes no API call and writes no database rows.

```python
from common.bronze import BronzeStore

store = BronzeStore("data/bronze", "euroleague", "E2025")
resource = "v2/game_stats/31"
version = store.latest_path(resource)
if version is None:
    print("Resource is not stored")
else:
    original_bytes = store.read_bytes(resource)
    payload = store.read_json(resource)
    print(version)
    print(payload.keys() if isinstance(payload, dict) else type(payload).__name__)
```

`read_bytes` raises if the resource is absent. `read_json` returns its default
for absent/unreadable JSON; inspect the path and parse failure when diagnosing
a problem instead of treating None as an empty response.

## Trace a Silver row to the archive

Join the row's load_id to `silver.load_log` using competition, season and table
name, then read each path in `bronze_versions` relative to `data/bronze/`.
Those paths identify the versions used by the load, which may differ from today's
latest versions. Auxiliary lookup resources can appear alongside the main input.
See the [Silver provenance query](SILVER_CATALOG.md#provenance-row---replacement---exact-bronze-version).

For calculated Silver tables, bronze_versions is empty: follow the producing
module's Silver inputs. The load log does not record a complete snapshot of
upstream Silver load IDs. Gold omits these provenance columns entirely.

## Maintaining the resource inventory

Resource templates, query construction and refresh decisions are defined in
[scrapper.py](../api_requests/scrapper.py); dataset selection is defined in
[utils.py](../api_requests/utils.py). Containers and source-field paths consumed
by Silver are in RawSeason/FlatSeason and
[flat_schema.py](../postgres_etl/flat_schema.py). Add or change a resource here
when those contracts change, and update the Silver lineage alongside it.
