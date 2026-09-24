# Build Plan

List the features that make up your project, high level and in rough build order.
Keep each item to one line; the details come later in `/feature`.

Plain bullets are fine. When both planning docs are ready, run `/overview`.
It adds tracking numbers and checkboxes to your feature list before generating
the project overview.

Run `/feature` to spec the next unchecked item, or `/feature 2` to pick one.
Keep completed items checked and append new features as the project grows.
Do not renumber completed features; their archived specs refer to those IDs.

Scaffolding the app and prototyping its look are pre-build steps, not features.
Start with your first real slice of functionality.

## Your features

Items 1-8 were already shipped when the Blueprint was adopted (2026-09-24).

- [x] 1. **Bronze fetch** - rate-limited download of v2/v3 plus live play-by-play and shots into exact, gzipped, versioned files with a request manifest
- [x] 2. **Current-season refresh** - re-fetch recent rounds' standings, stats and rosters automatically; daily re-check of season-level data
- [x] 3. **Local PostgreSQL load** - typed `etl_flat_*` tables from bronze with dry run and post-load quality checks
- [x] 4. **Source-problem handling** - unrecorded stats as NULL with `game_stat_gaps`, forfeits, derived game status, attendance notes, live player id matching
- [x] 5. **Neon publish** - replace a season in one transaction with a shrink guard, re-runnable
- [x] 6. **One-command refresh** - `pipeline.py` fetch, load and publish, skipped when nothing changed
- [x] 7. **CSV export** - local tables to one CSV per season and table
- [x] 8. **Full EuroLeague history** - E2000-E2025 downloaded and loaded locally with 0 quality errors
- [ ] 9. **Standings app table** - one page-shaped standings table published to Neon, replacing the 7 standings tables the app reads (coordinated with the web-app repo)
- [ ] 10. **Scheduled refresh** - Windows Task Scheduler runs `pipeline.py` nightly and about every 2 h on game days, with logs and failure visibility
- [ ] 11. **Records tables** - precomputed player-season, single-game and team-season records, excluding forfeits, instead of computing them in the Express API
- [ ] 12. **Coverage and team season stats** - precomputed coverage counts and team season aggregates for the app
- [ ] 13. **Postseason series** - play-in, playoff and Final Four matchups derived from games
- [ ] 14. **Player careers** - cross-season player dimension on `person_code` for careers, archives and head-to-head
- [ ] 15. **Historical seasons in Neon** - publish older seasons once Neon storage allows (app tables for all seasons are about 237 MB)
- [ ] 16. **Clean app schema** - rename `etl_flat_*` to clean names in a Neon `app` schema with a read-only role, coordinated with the web app
- [ ] 17. **Dependencies and CI** - `requirements.txt` and an automatic test run so the project installs and verifies anywhere
- [ ] 18. **EuroCup** - download, load and publish EuroCup seasons
- [ ] 19. **Analytics layer** - play-by-play and shot features, possessions and reports, local only (never Neon)

> TODO (confirm): the order of items 11-15 is a proposal; item 15 depends on your
> Neon plan's storage limit.
