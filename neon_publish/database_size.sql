-- Read-only Neon size check. Run it in the Neon SQL editor; it writes nothing.
-- The free tier allows 512 MB of storage per project, so also check the project's
-- storage figure on the Neon dashboard if the project has other databases or branches.

-- Whole database size.
SELECT pg_size_pretty(pg_database_size(current_database())) AS database_size,
       round(pg_database_size(current_database()) / 1048576.0, 1) AS size_mb;

-- Ten largest tables, including their indexes.
SELECT schemaname || '.' || relname AS table_name,
       pg_size_pretty(pg_total_relation_size(relid)) AS total_size,
       round(pg_total_relation_size(relid) / 1048576.0, 1) AS size_mb
FROM pg_catalog.pg_statio_user_tables
ORDER BY pg_total_relation_size(relid) DESC
LIMIT 10;
