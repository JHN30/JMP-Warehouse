"""Gold registry, CLI, transactions, and read-only quality checks."""

import contextlib
import io
import unittest
from pathlib import Path
from unittest.mock import patch

from gold_etl import main
from gold_etl.loader import replace_scope
from gold_etl.quality import check_records_scope, check_scope, check_series_scope
from gold_etl.schema import (AGGREGATE_NAMES, DERIVED_NAMES, GAME_ADVANCED_NAMES, GAME_COURT_NAMES, GAME_PBP_NAMES, GOLD_TABLES,
                             PLAYER_STATS, RECORDS_TABLES, ROUND_NAMES, SOURCE_NAMES, TABLES,
                             columns, count_sql, create_table_sql)
from postgres_etl.flat_schema import TABLES as SILVER_TABLES


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self.rowcount = 0
        self.answer = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, query, params=None):
        self.connection.statements.append((query, params))
        if query.startswith("INSERT INTO"):
            if self.connection.fail_insert:
                raise RuntimeError("insert failed")
            self.rowcount = self.connection.source_count
        elif query.startswith("SELECT season_code"):
            self.answer = [("E2025",), ("E2026",)]
        elif query.startswith("SELECT to_regclass"):
            self.answer = [("gold.games" if self.connection.table_exists else None,)]
        elif query.startswith("SELECT count(*)"):
            self.answer = [(self.connection.source_count if "silver." in query else
                            self.connection.gold_count,)]
        elif query.startswith("SELECT EXISTS"):
            self.answer = [(self.connection.values_differ,)]

    def fetchone(self):
        return self.answer[0]

    def fetchall(self):
        return self.answer


class FakeConnection:
    def __init__(self, source_count=2, gold_count=2):
        self.source_count = source_count
        self.gold_count = gold_count
        self.table_exists = True
        self.values_differ = False
        self.fail_insert = False
        self.statements = []
        self.commits = 0
        self.rollbacks = 0
        self.readonly = False
        self.closed = False

    def cursor(self):
        return FakeCursor(self)

    def __enter__(self):
        return self

    def __exit__(self, kind, *_):
        if kind:
            self.rollbacks += 1
        else:
            self.commits += 1
        return False

    def set_session(self, readonly, isolation_level):
        self.readonly = readonly
        assert isolation_level == "REPEATABLE READ"

    def close(self):
        self.closed = True


class SchemaTests(unittest.TestCase):
    def test_records_and_series_contract(self):
        self.assertEqual(tuple(RECORDS_TABLES), (
            "app_records_player_seasons", "app_records_single_games",
            "app_records_team_seasons"))
        self.assertEqual(GOLD_TABLES["app_postseason_series"].key,
                         ("competition_code", "season_code", "phase_code",
                          "club_a_code", "club_b_code"))
        for name in RECORDS_TABLES:
            with self.subTest(name=name):
                self.assertEqual(GOLD_TABLES[name].key,
                                 ("competition_code", "metric", "rank_ordinal"))
                self.assertEqual(GOLD_TABLES[name].fields[-1].kind, "NUMERIC NOT NULL")
                self.assertIn('PRIMARY KEY ("competition_code", "metric", "rank_ordinal")',
                              create_table_sql(name))
        self.assertEqual(columns("app_records_player_seasons"),
                         ("competition_code", "metric", "rank_ordinal", "season_code",
                          "person_key", "player_name", "club_code", "club_name", "value"))
        self.assertEqual(columns("app_records_single_games"),
                         ("competition_code", "metric", "rank_ordinal", "season_code",
                          "game_code", "scheduled_at", "person_key", "player_name",
                          "club_code", "club_name", "value"))
        self.assertEqual(columns("app_records_team_seasons"),
                         ("competition_code", "metric", "rank_ordinal", "season_code",
                          "club_code", "club_name", "value"))
        self.assertEqual(GOLD_TABLES["app_postseason_series"].fields[-1].kind,
                         "JSONB NOT NULL")

    def test_contract_has_exact_source_tables_fields_and_keys(self):
        self.assertEqual(len(SOURCE_NAMES), 16)
        self.assertEqual(len(TABLES), 16)
        self.assertEqual(len(PLAYER_STATS), 4)
        for name in SOURCE_NAMES:
            self.assertIs(TABLES[name], SILVER_TABLES[name])
            self.assertEqual(columns(name), tuple(field.name for field in SILVER_TABLES[name].fields))
            self.assertNotIn("load_id", columns(name))
            self.assertNotIn("loaded_at", columns(name))
            ddl = create_table_sql(name)
            self.assertIn(f'gold."{name}"', ddl)
            self.assertIn("PRIMARY KEY", ddl)
            self.assertNotIn("load_id", ddl)
            self.assertNotIn("loaded_at", ddl)

    def test_player_slice_excludes_ps_in_both_schemas(self):
        for name in PLAYER_STATS:
            self.assertIn("phase_code\" <> 'PS'", count_sql(name, "silver"))
            self.assertIn("phase_code\" <> 'PS'", count_sql(name, "gold"))
        self.assertNotIn("'PS'", count_sql("games", "gold"))


class LoaderTests(unittest.TestCase):
    def test_copy_uses_explicit_fields_and_one_transaction(self):
        db = FakeConnection()
        self.assertEqual(replace_scope(db, "games", "E", "E2025"), 2)
        self.assertEqual((db.commits, db.rollbacks), (1, 0))
        sql = [query for query, _ in db.statements]
        self.assertEqual(sql[0], "CREATE SCHEMA IF NOT EXISTS gold")
        self.assertTrue(sql[1].startswith("CREATE TABLE IF NOT EXISTS gold."))
        self.assertTrue(sql[2].startswith('DELETE FROM gold."games"'))
        self.assertTrue(sql[3].startswith('INSERT INTO gold."games"'))
        self.assertIn('FROM silver."games"', sql[3])
        self.assertNotIn("load_id", sql[3])
        self.assertEqual(db.statements[2][1], ("E", "E2025"))
        self.assertEqual(db.statements[3][1], ("E", "E2025"))
        self.assertFalse(any("DELETE FROM silver" in query or "neon" in query.lower()
                             for query in sql))

    def test_zero_source_clears_scope_and_rerun_does_not_append(self):
        db = FakeConnection(source_count=0)
        self.assertEqual(replace_scope(db, "games", "E", "E2025"), 0)
        db.source_count = 2
        self.assertEqual(replace_scope(db, "games", "E", "E2025"), 2)
        self.assertEqual(db.commits, 2)
        self.assertEqual(sum(query.startswith('DELETE FROM gold."games"')
                             for query, _ in db.statements), 2)

    def test_insert_failure_rolls_back_prior_scope(self):
        db = FakeConnection()
        db.fail_insert = True
        with self.assertRaisesRegex(RuntimeError, "insert failed"):
            replace_scope(db, "games", "E", "E2025")
        self.assertEqual((db.commits, db.rollbacks), (0, 1))

    def test_player_replace_preserves_ps_slice(self):
        db = FakeConnection()
        replace_scope(db, "season_player_stats_misc", "E", "E2025")
        for query, _ in db.statements[-2:]:
            self.assertIn("phase_code\" <> 'PS'", query)


class QualityTests(unittest.TestCase):
    def test_records_and_series_detect_missing_keys_and_value_drift(self):
        db = FakeConnection()
        record = {field: None for field in columns("app_records_team_seasons")}
        record.update(competition_code="E", metric="points", rank_ordinal=1,
                      season_code="E2025", club_code="A", value=90)
        series = {field: None for field in columns("app_postseason_series")}
        series.update(competition_code="E", season_code="E2025", phase_code="PO",
                      club_a_code="A", club_b_code="B", games_played=1,
                      club_a_wins=1, club_b_wins=0, games=[{"gameCode": 1}])
        with db.cursor() as cursor:
            db.table_exists = False
            self.assertIn("missing", check_records_scope(cursor,
                          "app_records_team_seasons", "E")[0])
            self.assertIn("missing", check_series_scope(cursor, "E", "E2025")[0])
            db.table_exists = True
            with patch("gold_etl.quality.read_record_rows", return_value=[record]), \
                    patch("gold_etl.quality._dict_rows", return_value=[]):
                self.assertIn("keys differ", check_records_scope(cursor,
                              "app_records_team_seasons", "E")[0])
            with patch("gold_etl.quality.read_record_rows", return_value=[record]), \
                    patch("gold_etl.quality._dict_rows",
                          return_value=[{**record, "value": 91}]):
                self.assertIn("values differ", check_records_scope(cursor,
                              "app_records_team_seasons", "E")[0])
            with patch("gold_etl.quality.read_series_rows", return_value=[series]), \
                    patch("gold_etl.quality._dict_rows",
                          return_value=[{**series, "games": [{"gameCode": 2}]}]):
                self.assertIn("games differ", check_series_scope(cursor,
                              "E", "E2025")[0])

    def test_missing_table(self):
        db = FakeConnection()
        db.table_exists = False
        with db.cursor() as cursor:
            self.assertEqual(check_scope(cursor, "games", "E", "E2025"),
                             ["gold.games is missing"])
        self.assertEqual(len(db.statements), 1)

    def test_count_and_value_mismatch(self):
        db = FakeConnection(source_count=2, gold_count=1)
        db.values_differ = True
        with db.cursor() as cursor:
            issues = check_scope(cursor, "games", "E", "E2025")
        self.assertEqual(len(issues), 2)
        self.assertIn("1 rows; silver has 2", issues[0])
        self.assertIn("source-column values differ", issues[1])
        self.assertIn("EXCEPT", db.statements[-1][0])
        self.assertEqual(db.statements[-1][1], ("E", "E2025", "E", "E2025"))

    def test_equal_scope(self):
        db = FakeConnection()
        with db.cursor() as cursor:
            self.assertEqual(check_scope(cursor, "games", "E", "E2025"), [])


class CliTests(unittest.TestCase):
    def test_records_run_once_across_selected_seasons(self):
        names = tuple(RECORDS_TABLES)
        with patch.object(main, "replace_records_scope", return_value=200) as replace:
            code, out, _, db = self.run_cli(["-sc", "all", "-tb", *names])
        self.assertEqual(code, 0)
        self.assertEqual(replace.call_count, 3)
        self.assertEqual([call.args[1:] for call in replace.call_args_list],
                         [(name, "E") for name in names])
        self.assertIn("Records scope: all locally loaded EuroLeague seasons", out)
        with patch.object(main, "read_record_rows", return_value=[{}]):
            code, out, _, db = self.run_cli(["-sc", "2025", "-tb", names[0],
                                             "--dry-run"])
        self.assertEqual(code, 0)
        self.assertTrue(db.readonly)
        self.assertIn("all seasons: 1 derived rows", out)
        with patch.object(main, "check_records_scope", return_value=["record drift"]):
            code, _, err, db = self.run_cli(["-sc", "2025", "-tb", names[0],
                                             "--quality-only"])
        self.assertEqual(code, 1)
        self.assertTrue(db.readonly)
        self.assertIn("record drift", err)

    def test_series_scopes_and_eurocup_records_rejected(self):
        with patch.object(main, "replace_series_scope", return_value=2) as replace:
            code, out, _, db = self.run_cli(["-sc", "all", "-tb",
                                             "app_postseason_series"])
        self.assertEqual(code, 0)
        self.assertEqual([call.args[1:] for call in replace.call_args_list],
                         [("E", "E2025"), ("E", "E2026")])
        with patch.object(main, "read_series_rows", return_value=[{}]):
            code, out, _, db = self.run_cli(["-sc", "2025", "-tb",
                                             "app_postseason_series", "--dry-run"])
        self.assertEqual(code, 0)
        self.assertTrue(db.readonly)
        with patch.object(main, "check_series_scope", return_value=["series drift"]):
            code, _, err, db = self.run_cli(["-sc", "2025", "-tb",
                                             "app_postseason_series", "--quality-only"])
        self.assertEqual(code, 1)
        self.assertTrue(db.readonly)
        self.assertIn("series drift", err)
        with contextlib.redirect_stderr(io.StringIO()) as stderr:
            with self.assertRaises(SystemExit):
                main.main(["-cp", "eurocup", "-tb", "app_records_single_games"])
        self.assertIn("EuroCup records are not supported", stderr.getvalue())

    def run_cli(self, args, db=None):
        db = db or FakeConnection()
        out, err = io.StringIO(), io.StringIO()
        with patch.object(main, "connect", return_value=db), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main.main(args)
        return code, out.getvalue(), err.getvalue(), db

    def test_list_tables_without_connection(self):
        with patch.object(main, "connect") as connect, \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main.main(["--list-tables"]), 0)
        connect.assert_not_called()
        self.assertEqual(output.getvalue().splitlines(), [*SOURCE_NAMES, *DERIVED_NAMES, *ROUND_NAMES, *GAME_ADVANCED_NAMES,
                          *GAME_PBP_NAMES, *GAME_COURT_NAMES])

    def test_dry_run_is_read_only_and_reports_counts(self):
        code, out, _, db = self.run_cli(["-sc", "2025", "-tb", "games", "--dry-run"])
        self.assertEqual(code, 0)
        self.assertTrue(db.readonly)
        self.assertIn("silver.games E2025: 2 source rows", out)
        self.assertFalse(any(query.startswith(("CREATE", "DELETE", "INSERT"))
                             for query, _ in db.statements))
        self.assertTrue(db.closed)

    def test_all_uses_local_silver_seasons(self):
        code, out, _, db = self.run_cli(["-sc", "all", "-tb", "games", "--dry-run"])
        self.assertEqual(code, 0)
        self.assertIn("Seasons: E2025, E2026", out)
        self.assertEqual(sum("SELECT count(*)" in query for query, _ in db.statements), 2)

    def test_missing_season_skips_before_write(self):
        code, out, _, db = self.run_cli(["-sc", "2024", "2025", "-tb", "games"])
        self.assertEqual(code, 0)
        self.assertIn("Not loaded in Silver; skipping: E2024", out)
        self.assertEqual(sum(query.startswith("DELETE") for query, _ in db.statements), 1)

    def test_no_available_selection_and_unknown_table(self):
        code, _, err, db = self.run_cli(["-sc", "2024", "-tb", "games"])
        self.assertEqual(code, 1)
        self.assertIn("No requested euroleague seasons are available", err)
        self.assertFalse(any(query.startswith("DELETE") for query, _ in db.statements))
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                main.main(["-tb", "bogus"])

    def test_quality_only_is_read_only_and_reports_failures(self):
        db = FakeConnection(gold_count=1)
        code, out, err, db = self.run_cli(["-sc", "2025", "-tb", "games",
                                           "--quality-only"], db)
        self.assertEqual(code, 1)
        self.assertTrue(db.readonly)
        self.assertIn("Gold quality: failed", out)
        self.assertIn("silver has 2", err)
        self.assertFalse(any(query.startswith(("CREATE", "DELETE", "INSERT"))
                             for query, _ in db.statements))

    def test_player_table_selection_includes_ps_dry_run_and_load(self):
        name = "season_player_stats_traditional"
        with patch.object(main, "read_postseason_rows", return_value={name: [{}, {}]}):
            code, out, _, db = self.run_cli(["-sc", "2025", "-tb", name,
                                             "--dry-run"])
        self.assertEqual(code, 0)
        self.assertTrue(db.readonly)
        self.assertIn(f"gold.{name} PS E2025: 2 derived rows", out)
        with patch.object(main, "replace_postseason_scope", return_value=2) as replace_ps:
            code, out, _, db = self.run_cli(["-sc", "2025", "-tb", name])
        self.assertEqual(code, 0)
        self.assertIn(f"gold.{name} PS E2025: 2 derived rows", out)
        replace_ps.assert_called_once_with(db, name, "E", "E2025")

    def test_missing_player_season_never_replaces_its_ps_slice(self):
        name = "season_player_stats_misc"
        with patch.object(main, "replace_postseason_scope", return_value=0) as replace_ps:
            code, out, _, db = self.run_cli(["-sc", "2024", "2025", "-tb", name])
        self.assertEqual(code, 0)
        self.assertIn("Not loaded in Silver; skipping: E2024", out)
        replace_ps.assert_called_once_with(db, name, "E", "E2025")

    def test_player_quality_checks_ps_slice_read_only(self):
        name = "season_player_stats_misc"
        with patch.object(main, "check_postseason_scope", return_value=["bad PS"]):
            code, _, err, db = self.run_cli(["-sc", "2025", "-tb", name,
                                             "--quality-only"])
        self.assertEqual(code, 1)
        self.assertTrue(db.readonly)
        self.assertIn("bad PS", err)

    def test_standings_selection_and_read_only_modes(self):
        with patch.object(main, "read_standings_rows", return_value=[{}, {}]):
            code, out, _, db = self.run_cli(["-sc", "2025", "-tb", "app_standings",
                                             "--dry-run"])
        self.assertEqual(code, 0)

        self.assertTrue(db.readonly)
        self.assertIn("gold.app_standings E2025: 2 derived rows", out)
        self.assertFalse(any(q.startswith(("CREATE", "DELETE", "INSERT"))
                             for q, _ in db.statements))
        with patch.object(main, "check_standings_scope", return_value=["bad standings"]), \
                patch.object(main, "check_standings_feeds", return_value=["streaks lags"]):
            code, out, err, db = self.run_cli(["-sc", "2025", "-tb", "app_standings",
                                               "--quality-only"])
        self.assertEqual(code, 1)
        self.assertTrue(db.readonly)
        self.assertIn("bad standings", err)
        self.assertIn("WARN streaks lags", out)
        with patch.object(main, "check_standings_scope", return_value=[]), \
                patch.object(main, "check_standings_feeds", return_value=["streaks lags"]):
            code, out, _, _ = self.run_cli(["-sc", "2025", "-tb", "app_standings",
                                            "--quality-only"])
        self.assertEqual(code, 0)  # a lagging feed warns; it does not block the publish
        self.assertIn("WARN streaks lags", out)
        with patch.object(main, "replace_standings_scope", return_value=2) as replace:
            code, out, _, db = self.run_cli(["-sc", "2025", "-tb", "app_standings"])
        self.assertEqual(code, 0)
        self.assertIn("gold.app_standings E2025: 2 rows", out)
        replace.assert_called_once_with(db, "E", "E2025")

    def test_aggregate_selection_and_read_only_modes(self):
        for name in AGGREGATE_NAMES:
            with self.subTest(name=name):
                with patch.object(main, "read_aggregate_rows", return_value=[{}]):
                    code, out, _, db = self.run_cli(["-sc", "2025", "-tb", name,
                                                     "--dry-run"])
                self.assertEqual(code, 0)
                self.assertTrue(db.readonly)
                self.assertIn(f"gold.{name} E2025: 1 derived rows", out)
                self.assertFalse(any(q.startswith(("CREATE", "DELETE", "INSERT"))
                                     for q, _ in db.statements))
                with patch.object(main, "check_aggregate_scope", return_value=["bad"]):
                    code, _, err, db = self.run_cli(["-sc", "2025", "-tb", name,
                                                     "--quality-only"])
                self.assertEqual(code, 1)
                self.assertTrue(db.readonly)
                self.assertIn("bad", err)
                with patch.object(main, "replace_aggregate_scope", return_value=1) as load:
                    code, out, _, db = self.run_cli(["-sc", "2025", "-tb", name])
                self.assertEqual(code, 0)
                load.assert_called_once_with(db, name, "E", "E2025")


if __name__ == "__main__":
    unittest.main()
