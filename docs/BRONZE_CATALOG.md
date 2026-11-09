# Bronze data catalog

Bronze is the file archive of original API response bodies. This catalog describes what is stored: the file layout and version identity, the response container of each resource, the manifest, and which [Silver tables](SILVER_CATALOG.md) each resource feeds. How and when the fetcher requests each resource is described in [api_requests/README.md](../api_requests/README.md).

Checked against the code on 2026-10-20, with EuroLeague examples. It does not claim that every resource exists for every game or that any response is complete. Bronze responses are JSON documents: they have no SQL types, primary keys or Silver's `NULL` normalization.

## Contents

- [Storage and version identity](#storage-and-version-identity)
- [Notation](#notation)
- [v2 catalog, profiles, fixtures and box scores](#v2-catalog-profiles-fixtures-and-box-scores)
- [v3 player and team season statistics](#v3-player-and-team-season-statistics)
- [v3 official standings](#v3-official-standings)
- [Live events and shots](#live-events-and-shots)
- [Freshness of stored versions](#freshness-of-stored-versions)
- [Manifest and operational files](#manifest-and-operational-files)
- [Reading a stored response](#reading-a-stored-response)
- [Tracing a Silver row to the archive](#tracing-a-silver-row-to-the-archive)
- [Maintaining this catalog](#maintaining-this-catalog)

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

- `_catalog` holds competition-wide resources. All other resource paths in this document are relative to a season directory such as `E2025/`.
- EuroCup uses the same layout under `data/bronze/eurocup/` with `U<year>` seasons (U2000-U2026; U2000 and U2001 are empty in the API).
- `<fetched_at>` is a UTC timestamp in `YYYYMMDDTHHMMSSffffffZ` format.
- `<sha16>` is the first 16 hexadecimal characters of the SHA-256 of the uncompressed response bytes.

### How versions are written

1. The API client passes the raw `response.content` to the store. The JSON is not reformatted or cleaned, so decompressing a version returns exactly the bytes received.
2. A new version is written only when its hash prefix differs from the **latest** version's prefix. This is not global deduplication: a response sequence A → B → A produces three files.
3. The file is written to a temporary name and atomically renamed into place. Versions are never overwritten.
4. Readers take the lexicographically last filename in a resource directory as the current version.

Because the hash covers bytes, a change in whitespace or field order creates a new version even when the parsed objects are equivalent.

Paths such as `v2/games.json` in the parser code (`RawSeason`) are logical handles. The archive itself stores `v2/games/<version>.json.gz`; there is no single mutable `games.json`.

Implementation: [common/bronze.py](../common/bronze.py), [api_client.py](../api_requests/api_client.py), [raw_transform.py](../postgres_etl/raw_transform.py).

## Notation

| Placeholder | Meaning |
| --- | --- |
| `{s}` | Season code, for example `E2025` or `U2025` |
| `{g}` | Game code within the season |
| `{club}` | Club code from the season's clubs or fixtures |
| `{phase}` | `all`, or a phase seen in played fixtures such as `RS`, `TS`, `PI`, `PO` or `FF`. There is no `PS` request; `PS` rows are built in Gold. |
| `{mode}` | `accumulated` or `perGame` |
| `{r}` | Round number from played group-phase fixtures |
| `offset_NNNNNN` | Zero-padded people-page offset, starting at `000000` |

Endpoints and hosts for each dataset are listed in the [api_requests README](../api_requests/README.md#endpoints-and-bronze-paths). They describe the fetcher's implemented contract, not independently revalidated API documentation.

## v2 catalog, profiles, fixtures and box scores

| Resource | Response container and contents | Silver tables |
| --- | --- | --- |
| `_catalog/v2/seasons` | `data[]`: season code, year, names, dates and winner. One response lists every season; Silver selects one. | [`seasons`](SILVER_TABLE_REFERENCE.md#seasons) |
| `v2/games` | `data[]`: scheduled and played fixtures, local and road clubs and scores, phase, group and round, dates, venue, attendance, `referee1`-`referee4`, and partial scores per side. | [`games`](SILVER_TABLE_REFERENCE.md#games), [`game_officials`](SILVER_TABLE_REFERENCE.md#game_officials), [`game_period_scores`](SILVER_TABLE_REFERENCE.md#game_period_scores) |
| `v2/clubs` | `data[]`: club names, codes, crests, country, contact, venue and sponsor. | [`clubs`](SILVER_TABLE_REFERENCE.md#clubs) |
| `v2/rounds` | `data[]`: phase, round, index, source name, first and last game dates. | [`rounds`](SILVER_TABLE_REFERENCE.md#rounds) |
| `v2/season_people_pages/offset_NNNNNN` | `data[]` plus `total`: registration entries with person profile and club and role context. Includes coaches, staff and officials. | [`people`](SILVER_TABLE_REFERENCE.md#people), [`registrations`](SILVER_TABLE_REFERENCE.md#registrations) |
| `v2/game_stats/{g}` | `local` and `road` objects, each with `players[]`, `team`, `total` and `coach`. Player entries hold `player` (registration and profile) and `stats`. | [`game_player_stats`](SILVER_TABLE_REFERENCE.md#game_player_stats), [`game_team_stats`](SILVER_TABLE_REFERENCE.md#game_team_stats), [`game_stat_gaps`](SILVER_TABLE_REFERENCE.md#game_stat_gaps) |
| `v2/rosters/{club}` | Archive only: no longer fetched or loaded. In every season E2000-E2026 each roster entry was already in the people pages with identical values. | none |

Notes:

- These resources cover E2000 onward, subject to the actual data.
- The fixture list keeps future games. Per-game statistics exist only for fixtures marked played.
- A played forfeit can have an empty player box score. The response stays intact, and Silver records `stat_name = '*'` in `game_stat_gaps` instead of inventing player rows.
- **People pages:** the endpoint can return 500 entries even when asked for 1000, so the fetcher advances by the entries received and checks the reported `total`. Each page is its own versioned resource. The loader combines the pages, deduplicates people and registrations, and ignores offsets beyond the current `total`.

## v3 player and team season statistics

All six feeds are stored as `v3/season_stats/{feed}_{phase}_{mode}`. Responses hold `players[]` or `teams[]`; each entry combines profile or team context with the feed's measures.

| Feed | Main measures | Silver table |
| --- | --- | --- |
| `players_traditional` | Games, minutes, points, shooting, rebounds, assists, steals, turnovers, blocks, fouls, PIR | [`season_player_stats_traditional`](SILVER_TABLE_REFERENCE.md#season_player_stats_traditional) |
| `players_advanced` | API eFG%, TS% and rebound percentages, assist and turnover ratios, attempt ratios, free-throw rate, possessions | [`season_player_stats_advanced`](SILVER_TABLE_REFERENCE.md#season_player_stats_advanced) |
| `players_scoring` | Shot mix, shares and rates, points-source percentages | [`season_player_stats_scoring`](SILVER_TABLE_REFERENCE.md#season_player_stats_scoring) |
| `players_misc` | Games, starts, wins and losses, minutes, double and triple doubles | [`season_player_stats_misc`](SILVER_TABLE_REFERENCE.md#season_player_stats_misc) |
| `teams_traditional` | Team totals and averages, shooting percentages | [`season_team_stats_traditional`](SILVER_TABLE_REFERENCE.md#season_team_stats_traditional) |
| `teams_advanced` | Team efficiency, rebounding, assist and turnover, shooting mix, scoring sources | [`season_team_stats_advanced`](SILVER_TABLE_REFERENCE.md#season_team_stats_advanced) |

### Request parameters

- All feeds: `SeasonMode=Single`, `SeasonCode={s}`, `StatisticMode={mode}`, `Limit=1000`, plus `PhaseTypeCode` for a single phase. The `all` request omits the phase filter.
- Player feeds also sort: `Statistic=timePlayed` (traditional, advanced) or `gamesPlayed` (scoring, misc), descending, with `StatisticSortMode={mode}`. Team feeds omit these sort keys.
- Player feeds are stored in both modes; team feeds in `accumulated` only, because their only reader is Gold's accumulated cross-check.
- When a snapshot is stale, the fetcher may use an equivalent `SeasonMode=Range` key. The resource name stays the same, and the manifest records the parameters actually used.
- There is no pagination loop: `Limit=1000` is simply the request. Do not infer completeness from the limit.

### Interpreting the feeds

- Entry order is stored as `entry_ordinal`. It is a feed position, not a permanent ID.
- Transferred players can have a semicolon-separated team code such as `BAS;TEL`. It is kept as received and does not identify one club.
- The API can omit players below its minimum games from `perGame`. Bronze and Silver keep what was returned; missing `perGame` rows, qualification flags and combined postseason rows are added in Gold.
- The team feeds stay local as reference values and are not published. Their ratio definitions can differ from the calculated Gold measures; check the [glossary](STAT_GLOSSARY.md) instead of assuming equal labels mean equal formulas.
- Opponents feeds (`teams/opponentsTraditional`, `teams/opponentsAdvanced`) and team per-game files fetched before 2026-10-25 remain in the archive and are not loaded. Opponent totals in `app_team_season_stats` come from the box scores.

## v3 official standings

Each standings response holds `teams[]` with club, group, official position and record fields, plus the feed's own values. The resource name `v3/standings/{phase}_{r}_{feed}` includes the phase, although the URL identifies only the round.

| Feed | Additional contents | Silver tables | In `app_standings` |
| --- | --- | --- | --- |
| `basicstandings` | Points, home, away, neutral, overtime and last-ten records; `last5Form[]` | [`standings_basic`](SILVER_TABLE_REFERENCE.md#standings_basic), [`standings_basic_form`](SILVER_TABLE_REFERENCE.md#standings_basic_form) | `basic_*` columns and the ordered `form` JSON |
| `calendarstandings` | Calendar records and `streaks[]` with dates and win-loss text | [`standings_calendar`](SILVER_TABLE_REFERENCE.md#standings_calendar), [`standings_calendar_streaks`](SILVER_TABLE_REFERENCE.md#standings_calendar_streaks) | `calendar_*` columns and the `streak_history` JSON |
| `streaks` | Current and longest streaks; home, away and recent records | [`standings_streaks`](SILVER_TABLE_REFERENCE.md#standings_streaks) | `streaks_*` columns |
| `aheadbehind` | Results when ahead, behind or tied after Q1, half-time and Q3 | [`standings_ahead_behind`](SILVER_TABLE_REFERENCE.md#standings_ahead_behind) | `ahead_behind_*` columns |
| `margins` | Results by final margin and statistical comparison | [`standings_margins`](SILVER_TABLE_REFERENCE.md#standings_margins) | `margins_*` columns |

Only played **group-phase** rounds are requested (`phaseType.isGroupPhase` in the fixtures), so knockout phases have no standings by design. Official standings snapshots are separate from calculated team round totals, and historical rounds may not align exactly.

## Live events and shots

Live requests use `gamecode={g}&seasoncode={s}` and run only for played games from E2007 onward. Endpoint spelling and response field casing are kept as received.

| Resource | Response structure | Silver table |
| --- | --- | --- |
| `live/{g}/play_by_play` | Arrays `FirstQuarter`, `SecondQuarter`, `ThirdQuarter`, `ForthQuarter`, `ExtraTime`. Entries include `PLAYTYPE`, `PLAYER_ID`, `CODETEAM`, `NUMBEROFPLAY`, `MINUTE`, `MARKERTIME` and running scores. | [`play_by_play`](SILVER_TABLE_REFERENCE.md#play_by_play) |
| `live/{g}/shooting_charts` | `Rows[]`: `ID_ACTION`, `ID_PLAYER`, `TEAM`, `NUM_ANOT`, `POINTS`, coordinates, zone and fast-break, second-chance and off-turnover flags. | [`shots`](SILVER_TABLE_REFERENCE.md#shots) |

- **Overtime.** All overtime events share the `ExtraTime` array; the `MINUTE` value identifies the overtime number. Silver keeps the period label as text, and calculated tables order events by period rank, overtime number and event ordinal. `play_number` is not a chronological key.
- **Player identities.** Live player IDs sometimes disagree with the v2 box scores. Bronze keeps the original. Silver stores the raw `player_code`, the resolved `person_code` and the `person_code_method`, using box-score identities, club and jersey, normalized name and lookup fallbacks. The resolved `person_code` joins the box-score `person_key`; no simple prefix-removal rule guarantees a match.
- **Empty shots.** An HTTP 200 with `Rows: []` is stored as a successful response with no shots.
- **Gaps.** Missing clocks, unrecorded flags and unmatched players can prevent some calculated measures even when a response exists. The archive does not fill these gaps or standardize the coordinate system.

## Freshness of stored versions

The refresh rules are described in [api_requests/README.md](../api_requests/README.md#refreshing-the-current-season). What matters when reading the archive:

- Completed seasons and stored per-game detail are reused; they are not re-fetched.
- For the current season, mutable resources are re-fetched after hot games and on a schedule.
- A v3 answer that is worse than the stored version can be rejected, leaving the previous version as latest. With no previous version, a stale answer can still be stored and reported as behind the fixtures.

The latest stored version is therefore neither guaranteed complete nor necessarily the latest response the API returned.

## Manifest and operational files

Each scope has a `manifest.jsonl`, with one JSON object per logged request. Normal stored or unchanged responses have the fields below; error and rejected records have related but different shapes, so not every field appears on every line. Reusing a cached file without a request adds no entry, and individual HTTP retries are not all logged separately.

| Field | Meaning |
| --- | --- |
| `resource` | Logical path within the scope, such as `v2/game_stats/31` |
| `url` | The request or final response URL |
| `params` | Request parameters. The cache-busting `_` key can appear in `url` without being in this object. |
| `status_code` | HTTP status; `NULL` when no HTTP response was received |
| `fetched_at_utc` | UTC time of the store or log action (not the game time) |
| `sha256` | Full digest of the response bytes, for successful or rejected JSON answers |
| `bytes` | Uncompressed response length |
| `stored_as` | Filename of the new version when one was saved; `NULL` for unchanged, rejected or failed answers. Not a full path. |
| `rejected` | Why a stale or worse answer was rejected; absent on normal entries |
| `error` | Request or JSON failure details |

`stored_as: null` alone does not mean failure: check `status_code`, `error` and `rejected`, and the resource's latest stored file. Rejected answers are not saved as versions; the manifest keeps their hash, length and reason. Failed or non-JSON responses are logged as failures, not stored.

Other operational files (not API payloads):

| File | Contents |
| --- | --- |
| `failures.jsonl` | Failed requests |
| `refresh_state.json` | When mutable season resources were last checked |
| `runs/run_<timestamp>.json` | One run's summary |

## Reading a stored response

Run from the repository root. This reads local archive files only: no API call and no database writes.

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

`read_bytes` raises an error if the resource is absent. `read_json` returns its default for an absent or unreadable file, so when diagnosing a problem, check the path and parse errors instead of treating `None` as an empty response.

## Tracing a Silver row to the archive

1. Join the row's `load_id` to `silver.load_log` on competition, season and table name.
2. Read each path in `bronze_versions`, relative to `data/bronze/`.

Those paths are the versions the load used, which may be older than today's latest versions. Auxiliary lookups, such as box scores used to resolve live players, can appear next to the main input. The [Silver catalog](SILVER_CATALOG.md#provenance) has the query.

Calculated Silver tables have an empty `bronze_versions`; follow the producing script's Silver inputs instead. Gold drops these provenance columns.

## Maintaining this catalog

Resource templates, query construction and refresh decisions are in [scrapper.py](../api_requests/scrapper.py); dataset selection is in [utils.py](../api_requests/utils.py). The containers and field paths Silver reads are in `RawSeason`/`FlatSeason` and [flat_schema.py](../postgres_etl/flat_schema.py). When those change, update this catalog and the Silver lineage together.
