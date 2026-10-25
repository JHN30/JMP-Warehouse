-- Drop the seven Gold tables the web app no longer reads. The publisher stopped writing
-- them with the fix "Stop publishing tables the web app no longer reads".
-- Applied on Neon on 2026-10-26, after the owner confirmed the app deploy (commits
-- 04f65f5 and c713d64) that stopped reading them. Run as one transaction on the
-- direct Neon connection. The recurring publisher never executes this file.
-- No CASCADE: a view, foreign key or other object that still depends on one of these
-- tables stops the whole transaction and nothing is dropped.

-- Optional read-only check before applying: row counts of the seven tables.
-- SELECT 'app_coverage_games' AS t, count(*) FROM public.app_coverage_games
-- UNION ALL SELECT 'app_coverage_seasons', count(*) FROM public.app_coverage_seasons
-- UNION ALL SELECT 'app_team_round_stats', count(*) FROM public.app_team_round_stats
-- UNION ALL SELECT 'app_team_round_ratings', count(*) FROM public.app_team_round_ratings
-- UNION ALL SELECT 'app_team_round_splits', count(*) FROM public.app_team_round_splits
-- UNION ALL SELECT 'app_game_team_shot_zones', count(*) FROM public.app_game_team_shot_zones
-- UNION ALL SELECT 'app_team_shot_zone_stats', count(*) FROM public.app_team_shot_zone_stats;

BEGIN;
SET LOCAL lock_timeout = '15s';

DROP TABLE public.app_coverage_games;
DROP TABLE public.app_coverage_seasons;
DROP TABLE public.app_team_round_stats;
DROP TABLE public.app_team_round_ratings;
DROP TABLE public.app_team_round_splits;
DROP TABLE public.app_game_team_shot_zones;
DROP TABLE public.app_team_shot_zone_stats;

COMMIT;
