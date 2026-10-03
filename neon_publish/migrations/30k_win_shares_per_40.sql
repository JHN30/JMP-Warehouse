-- Neon migration: Win Shares rate per 40 minutes instead of 48. Renames the column on
-- the existing table (data and the API role's SELECT grant are kept); republish E2025 and
-- E2026 afterwards so the values use the 40-minute scale. Run as one transaction on the
-- direct Neon connection, and coordinate the web app change. The recurring publisher
-- never executes this file.
BEGIN;
SET LOCAL lock_timeout = '15s';

ALTER TABLE public.app_player_round_win_shares
    RENAME COLUMN "win_shares_per_48" TO "win_shares_per_40";

COMMIT;
