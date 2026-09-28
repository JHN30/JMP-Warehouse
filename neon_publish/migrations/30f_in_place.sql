-- One-time in-place Neon cutover. Review the live preflight and coordinate the web app before applying.
-- Run as one transaction on the direct Neon connection. The recurring publisher never executes this file.
BEGIN;
SET LOCAL lock_timeout = '15s';

ALTER TABLE public.app_registrations RENAME COLUMN dorsal TO jersey_number;
ALTER TABLE public.app_registrations RENAME COLUMN dorsal_raw TO jersey_number_raw;

ALTER TABLE public.app_game_player_stats RENAME COLUMN assistances TO assists;
ALTER TABLE public.app_game_player_stats RENAME COLUMN fouls_commited TO fouls_committed;
ALTER TABLE public.app_game_player_stats RENAME COLUMN fouls_received TO fouls_drawn;
ALTER TABLE public.app_game_player_stats RENAME COLUMN blocks_favour TO blocks;
ALTER TABLE public.app_game_player_stats RENAME COLUMN valuation TO pir;
ALTER TABLE public.app_game_player_stats RENAME COLUMN field_goals_made2 TO two_pointers_made;
ALTER TABLE public.app_game_player_stats RENAME COLUMN field_goals_attempted2 TO two_pointers_attempted;
ALTER TABLE public.app_game_player_stats RENAME COLUMN field_goals_made3 TO three_pointers_made;
ALTER TABLE public.app_game_player_stats RENAME COLUMN field_goals_attempted3 TO three_pointers_attempted;
ALTER TABLE public.app_game_player_stats RENAME COLUMN field_goals_made_total TO field_goals_made;
ALTER TABLE public.app_game_player_stats RENAME COLUMN field_goals_attempted_total TO field_goals_attempted;
ALTER TABLE public.app_game_player_stats RENAME COLUMN time_played TO seconds_played;
ALTER TABLE public.app_game_player_stats RENAME COLUMN dorsal TO jersey_number;

ALTER TABLE public.app_game_team_stats RENAME COLUMN assistances TO assists;
ALTER TABLE public.app_game_team_stats RENAME COLUMN fouls_commited TO fouls_committed;
ALTER TABLE public.app_game_team_stats RENAME COLUMN fouls_received TO fouls_drawn;
ALTER TABLE public.app_game_team_stats RENAME COLUMN blocks_favour TO blocks;
ALTER TABLE public.app_game_team_stats RENAME COLUMN valuation TO pir;
ALTER TABLE public.app_game_team_stats RENAME COLUMN field_goals_made2 TO two_pointers_made;
ALTER TABLE public.app_game_team_stats RENAME COLUMN field_goals_attempted2 TO two_pointers_attempted;
ALTER TABLE public.app_game_team_stats RENAME COLUMN field_goals_made3 TO three_pointers_made;
ALTER TABLE public.app_game_team_stats RENAME COLUMN field_goals_attempted3 TO three_pointers_attempted;
ALTER TABLE public.app_game_team_stats RENAME COLUMN field_goals_made_total TO field_goals_made;
ALTER TABLE public.app_game_team_stats RENAME COLUMN field_goals_attempted_total TO field_goals_attempted;
ALTER TABLE public.app_game_team_stats RENAME COLUMN time_played TO seconds_played;

ALTER TABLE public.app_season_stats_traditional RENAME TO app_season_player_stats_traditional;
ALTER TABLE public.app_season_player_stats_traditional RENAME COLUMN fouls_commited TO fouls_committed;
ALTER TABLE public.app_season_player_stats_traditional RENAME COLUMN points_scored TO points;
ALTER TABLE public.app_season_stats_advanced RENAME TO app_season_player_stats_advanced;
ALTER TABLE public.app_season_player_stats_advanced RENAME COLUMN possesions TO possessions;
ALTER TABLE public.app_season_stats_scoring RENAME TO app_season_player_stats_scoring;
ALTER TABLE public.app_season_stats_misc RENAME TO app_season_player_stats_misc;

ALTER TABLE public.app_play_by_play RENAME COLUMN dorsal TO jersey_number;

CREATE TABLE public.app_club_identities (
    competition_code TEXT NOT NULL,
    club_code TEXT NOT NULL,
    name TEXT,
    crest_url TEXT,
    country_code TEXT,
    country_name TEXT,
    first_season_code TEXT NOT NULL,
    last_season_code TEXT NOT NULL,
    seasons_played INTEGER NOT NULL,
    PRIMARY KEY (competition_code, club_code)
);

COMMIT;
