-- Neon migration for feature 30l: leaderboard qualification columns on the four season
-- player tables. Adds is_calculated, min_games and qualified (data and the API role's
-- table-level SELECT grant are kept). The defaults only fill the existing rows until the
-- publisher replaces them: publish E2024, E2025 and E2026 right after applying this file,
-- because until then every row reads min_games 0 and qualified false. Run as one
-- transaction on the direct Neon connection, and coordinate the web app change. The
-- recurring publisher never executes this file.
BEGIN;
SET LOCAL lock_timeout = '15s';

ALTER TABLE public.app_season_player_stats_traditional
    ADD COLUMN "is_calculated" BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN "min_games" INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN "qualified" BOOLEAN NOT NULL DEFAULT false;

ALTER TABLE public.app_season_player_stats_advanced
    ADD COLUMN "is_calculated" BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN "min_games" INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN "qualified" BOOLEAN NOT NULL DEFAULT false;

ALTER TABLE public.app_season_player_stats_scoring
    ADD COLUMN "is_calculated" BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN "min_games" INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN "qualified" BOOLEAN NOT NULL DEFAULT false;

ALTER TABLE public.app_season_player_stats_misc
    ADD COLUMN "is_calculated" BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN "min_games" INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN "qualified" BOOLEAN NOT NULL DEFAULT false;

COMMIT;
