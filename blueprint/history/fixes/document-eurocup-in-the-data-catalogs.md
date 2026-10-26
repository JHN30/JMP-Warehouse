# Fix: Document EuroCup in the data catalogs

**Type:** Fix
**Status:** verified
**Branch:** fix/document-eurocup-in-the-data-catalogs
**Fixes:** F-19

## The problem

Four catalogs still describe EuroLeague only, although EuroCup (`competition_code = 'U'`)
is in Bronze, Silver and Gold locally since feature 18:

| File | Stale text |
|---|---|
| `docs/BRONZE_CATALOG.md:1-8` | Title "EuroLeague Bronze data catalog"; "EuroCup documentation will be added when that work begins." Storage shows only `data/bronze/euroleague/`; endpoints only `/competitions/E/`; `{s}` is "EuroLeague season code". |
| `docs/SILVER_CATALOG.md:1-9` | Title "EuroLeague Silver data catalog"; "Scope is EuroLeague … EuroCup coverage and rule differences will be documented when that work begins." |
| `docs/DATA_CATALOG.md:8-9` | "currently documents EuroLeague coverage. EuroCup coverage and rule differences will be added …" |
| `docs/SILVER_TABLE_REFERENCE.md:1,8` and 33 column rows | Title "EuroLeague Silver table reference"; "Examples and coverage refer to EuroLeague only."; every `competition_code` row says "this catalog covers EuroLeague rows with E." |

`docs/GOLD_TABLE_REFERENCE.md`, `docs/DATA_DICTIONARY.md`, `README.md` and
`gold_etl/README.md` already describe EuroCup and are out of scope.

## The fix

Documentation only. No code, schema, table or test changes.

- **`SILVER_CATALOG.md`** holds the one EuroCup reference section, `## EuroCup`. The
  other catalogs link to it instead of repeating it. The section covers:
  - **Status:** local only. Bronze, Silver and Gold are built by
    `python pipeline.py -cp eurocup`, and nothing is published to Neon until the owner
    approves.
  - **Coverage:** U2002-U2026 games and box scores. U2000 and U2001 are empty in the API.
    Play-by-play and shots run U2007-U2026. U2026 is the season in progress.
  - **Phase codes per era**, from `gold_etl/qualification.py`: regular season `RS`, `TS`
    from U2016-U2020, and `L32`/`L16` group stages. Knockouts are `8F`, `4F`, `2F` and
    `Final`. In U2007, `L32` and `L16` were knockouts even though the API marks them as
    groups.
  - **Tie formats:** two-leg aggregate ties for the seasons and phases in
    `TWO_LEG_PHASES` (U2002-U2015), won on aggregate points. Best-of-3 from U2016.
    Single games otherwise.
  - **Known source quirks:**
    - Drawn first or second legs are allowed only inside a two-leg tie
      (`draw_without_two_leg_tie`).
    - U2019 was cancelled: its 12 unplayed `4F` games have `status = cancelled` and are
      left out of series.
    - The box-score points corrections (`points_corrected`) are in U2004 games 103 and
      138, and U2005 game 4.
    - U2021 has 6 unplayed games. Their status is checked during implementation.
- **`BRONZE_CATALOG.md`:**
  - Neutral title ("Bronze data catalog").
  - The intro names both competitions and links the Silver EuroCup section.
  - Storage notes `data/bronze/eurocup/` with `U<year>` seasons.
  - The API hosts note says the competition code is `E` or `U`.
  - `{s}` is "season code, for example E2025 or U2025".
  - Endpoint rows keep `/competitions/E/` as the example.
- **`DATA_CATALOG.md`:** replace the "currently documents EuroLeague" sentence with the
  scope (E published, U local only) and a link to the EuroCup section.
- **`SILVER_TABLE_REFERENCE.md`:**
  - Neutral title.
  - Line 8 says examples use EuroLeague and coverage includes EuroCup.
  - The 33 `competition_code` rows read "Competition identifier: E for EuroLeague, U for
    EuroCup." This matches the Silver wording, without Gold's Neon note, because Silver
    is never published.
- Keep each catalog's "checked on 2026-10-20" date for the EuroLeague contract. The
  EuroCup section states that it was checked on 2026-10-26 against local Silver.

Must not break:
- every relative link and anchor between the docs
- the existing EuroLeague content
- the `## ` section order other docs link to (the new section is appended before
  `## Coverage and interpretation`, so no anchor changes)

## Build steps

- [x] 1. Add the `## EuroCup` section to `SILVER_CATALOG.md` and update its intro.
  Before writing them, confirm every stated fact with a read-only query on local Silver
  and with `qualification.py`: season and game counts, phase codes per season, the
  play-by-play and shots range, the U2019 cancelled games, the U2021 unplayed games, and
  the drawn legs.
  **Done when:** the section exists, and every number in it matches a query output shown
  in the review.
- [x] 2. Update `BRONZE_CATALOG.md`, `DATA_CATALOG.md` and `SILVER_TABLE_REFERENCE.md` as
  above.
  **Done when:**
  - `grep -n "EuroCup documentation will be added\|will be documented when that work begins\|will be added when that implementation begins\|refer to EuroLeague only\|covers EuroLeague rows with E" docs/*.md`
    returns nothing.
  - A link check finds every relative `.md` link and `#anchor` in the four files
    resolving to an existing file and heading. This is a small read-only script in the
    scratchpad.
  - F-19 is marked `fixed`.

## Verify

- The stale-text grep above returns nothing.
- The link and anchor check passes for the four catalogs.
- Read the new `## EuroCup` section in `docs/SILVER_CATALOG.md`.

## Implementation notes

- The tie formats follow the owner-confirmed table in
  `blueprint/history/features/18c-eurocup-postseason.md`, not this spec's shorthand
  "best-of-3 from U2016". U2021-U2022 are single games, and U2023-U2025 play only `2F` and
  `Final` as best-of-three.
- U2021's 6 unplayed games are `RS` games with `status = cancelled`.
- The section sits after `## Coverage and interpretation` and before
  `## Provenance`. Adding a heading changes no existing anchor.
- The work went slightly beyond the spec in the same file, removing the same
  EuroLeague-only wording:
  - the 33 `season_code` rows ("Starting-year EuroLeague season code")
  - the `load_log` `competition_code` row


<!-- blueprint:completion {"schemaVersion":1,"specBytes":5967,"specSha256":"3a6d1bc092259f98045bb26cf0550a0fcd726cbd13dc72a377022a65fda25979","branch":"refs/heads/fix/document-eurocup-in-the-data-catalogs","head":"1d6aaebadd5ba4c3f87fee06fe077e1288b59d4a","baseRef":"refs/heads/main","baseCommit":"1d6aaebadd5ba4c3f87fee06fe077e1288b59d4a","sourceTree":"f0c427d3d6474d10259e5d46ca5a125788b6bd77","absentOptional":[]} -->

## Findings

### document-eurocup-in-the-data-catalogs/F-19 [P3] closed - Data catalogs still describe EuroLeague only

**File:** docs/BRONZE_CATALOG.md:8
**Found:** 2026-10-26 during feature 18a (doc search)
**Why it matters:** `docs/BRONZE_CATALOG.md:8`, `docs/SILVER_CATALOG.md:9`,
`docs/DATA_CATALOG.md:8` and `docs/SILVER_TABLE_REFERENCE.md:8` say EuroCup coverage
will be documented later, although EuroCup is now in Bronze, Silver and Gold locally.
**Suggested fix:** add EuroCup coverage (U2002-U2026; U2000-U2001 empty in the API),
its phase codes and format eras, and its known source gaps to the catalogs.
**Resolution:** fixed 2026-10-26 on fix/document-eurocup-in-the-data-catalogs: docs/SILVER_CATALOG.md has a new `## EuroCup` section covering status, coverage, phase codes, tie formats and source quirks, checked with read-only queries on local Silver. The Bronze, Gold and Silver-reference catalogs now name both competitions and link to it. The 34 `competition_code` and 33 `season_code` column rows no longer say EuroLeague only. The stale-text grep returns nothing, and all 340 relative links and anchors in the four files resolve. Closed 2026-10-26 by /audit (scope: F-19; lens: quality). I re-read the changed intros, the storage and host notes, and the new `## EuroCup` section against local Bronze (data/bronze/eurocup holds `_catalog` and U2000-U2026, with the same v2, v3 and live resource folders as EuroLeague), local Silver and the owner-confirmed format table in the 18c archive. The only other changes are the 67 column rows, 34 `competition_code` and 33 `season_code`; the diff numstat is 70/69, and the remaining lines are the title and intro. No stale wording or new defect remains.
