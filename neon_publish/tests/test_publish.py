"""Gold-to-Neon contract, transaction, CLI, and refresh regression tests."""

import io
import json
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest import mock

from gold_etl.schema import (DERIVED_NAMES, GAME_ADVANCED_NAMES, GAME_COURT_NAMES,
                             GAME_PBP_NAMES, PHYSICAL_TABLES as GOLD_TABLES, ROUND_NAMES, SOURCE_NAMES, physical_name)
from neon_publish import publish
from neon_publish.contract import (APP_TABLES, GAME_COURT_TABLES, GAME_PBP_TABLES,
                                   GAME_TABLES, GLOBAL_TABLES,
                                   NEW_TABLES,
                                   inspect_target,
                                   migration_sql, predicate, scope, target_name)
from neon_publish.main import main as publish_main
from pipeline import StageFacts, build_parser, build_summary, read_state, redactor, refresh, refresh_history


SOURCE_NAMES = tuple(map(physical_name, SOURCE_NAMES))
ROUND_NAMES = tuple(map(physical_name, ROUND_NAMES))
GAME_ADVANCED_NAMES = tuple(map(physical_name, GAME_ADVANCED_NAMES))
GAME_PBP_NAMES = tuple(map(physical_name, GAME_PBP_NAMES))
GAME_COURT_NAMES = tuple(map(physical_name, GAME_COURT_NAMES))


class ContractTests(unittest.TestCase):
    def test_every_gold_table_has_a_fixed_target_and_scope(self):
        self.assertEqual(APP_TABLES,
                         SOURCE_NAMES + DERIVED_NAMES + ROUND_NAMES + GAME_ADVANCED_NAMES
                         + GAME_PBP_NAMES + GAME_COURT_NAMES)
        self.assertEqual(len(APP_TABLES), 40)
        self.assertEqual(len({target_name(name) for name in APP_TABLES}), 40)
        self.assertEqual(len(GLOBAL_TABLES), 5)
        self.assertEqual(set(APP_TABLES), set(GOLD_TABLES))
        for name in APP_TABLES:
            self.assertEqual(target_name(name), name)
            self.assertEqual(scope(name, "E", "E2025"),
                             ("E",) if name in GLOBAL_TABLES else ("E", "E2025"))
            self.assertEqual(predicate(name), "competition_code = %s" if name in GLOBAL_TABLES
                             else "competition_code = %s AND season_code = %s")

    def test_shrink_and_game_diff(self):
        self.assertEqual(publish.shrink_problems({"app_games": 80}, {"app_games": 100}),
                         ["app_games: 100 -> 80 rows"])
        self.assertEqual(publish.shrink_problems({"app_games": 95}, {"app_games": 100}), [])
        self.assertEqual(publish.changed_games({1: (10, "a"), 2: (8, "b")},
                                               {1: (10, "a"), 3: (2, "c")}), ([2], [3]))

    def test_preflight_reports_missing_compatible_and_incompatible(self):
        missing = mock.MagicMock()
        missing.fetchone.return_value = (None,)
        self.assertEqual(inspect_target(missing, "app_games"),
                         ["public.app_games: missing table"])
        self.assertFalse(any("ALTER" in str(call) for call in missing.execute.call_args_list))

        spec = GOLD_TABLES["app_games"]
        columns = [(field.name, {"TEXT": "text", "INTEGER": "integer",
                                 "BOOLEAN": "boolean", "TIMESTAMP": "timestamp without time zone",
                                 "TIMESTAMPTZ": "timestamp with time zone"}[field.kind.split()[0]],
                    "NO" if "NOT NULL" in field.kind else "YES", None)
                   for field in spec.fields]
        key = ", ".join(spec.key)
        compatible = mock.MagicMock()
        compatible.fetchone.return_value = ("app_games",)
        compatible.fetchall.side_effect = [columns, [("p", f"PRIMARY KEY ({key})")]]
        self.assertEqual(inspect_target(compatible, "app_games"), [])
        incompatible = mock.MagicMock()
        incompatible.fetchone.return_value = ("app_games",)
        incompatible.fetchall.side_effect = [columns[:-1] + [("extra", "text", "NO", None)],
                                             [("p", "PRIMARY KEY (wrong)")]]
        issues = inspect_target(incompatible, "app_games")
        self.assertTrue(any("missing column" in issue for issue in issues))
        self.assertTrue(any("extra required column" in issue for issue in issues))
        self.assertTrue(any("primary key differs" in issue for issue in issues))


class PlayerQualificationTests(unittest.TestCase):
    """The three columns added to the four season player tables in 30l."""

    FLAGS = ("is_calculated", "min_games", "qualified")
    TYPES = {"TEXT": "text", "INTEGER": "integer", "NUMERIC": "numeric", "BOOLEAN": "boolean"}

    def present(self, name, skip=()):
        spec = GOLD_TABLES[name]
        columns = [(field.name, self.TYPES[field.kind.split()[0]],
                    "NO" if "NOT NULL" in field.kind or field.name in spec.key else "YES", None)
                   for field in spec.fields if field.name not in skip]
        cursor = mock.MagicMock()
        cursor.fetchone.return_value = (target_name(name),)
        cursor.fetchall.side_effect = [columns, [("p", f"PRIMARY KEY ({', '.join(spec.key)})")]]
        return cursor

    def test_published_columns_include_the_flags_after_the_feed_columns(self):
        for name in ("app_season_player_stats_traditional", "app_season_player_stats_advanced",
                     "app_season_player_stats_scoring", "app_season_player_stats_misc"):
            with self.subTest(table=name):
                fields = GOLD_TABLES[name].fields
                self.assertEqual(tuple(field.name for field in fields[-3:]), self.FLAGS)
                self.assertEqual([field.kind for field in fields[-3:]],
                                 ["BOOLEAN NOT NULL", "INTEGER NOT NULL", "BOOLEAN NOT NULL"])
                self.assertEqual(inspect_target(self.present(name), name), [])

    def test_a_neon_table_without_the_flags_fails_the_preflight(self):
        name = "app_season_player_stats_misc"
        issues = inspect_target(self.present(name, skip=self.FLAGS), name)
        for column in self.FLAGS:
            self.assertTrue(any(f"missing column {column} " in issue for issue in issues), column)

    def test_the_migration_adds_the_flags_to_all_four_tables_without_dropping(self):
        path = Path(__file__).resolve().parents[1] / "migrations" / "30l_player_stats_qualification.sql"
        sql = path.read_text(encoding="utf-8")
        self.assertEqual(sql.count("ALTER TABLE public.app_season_player_stats_"), 4)
        self.assertEqual(sql.count("ADD COLUMN"), 12)
        self.assertTrue(sql.rstrip().endswith("COMMIT;"))
        self.assertNotIn("DROP", sql)
        self.assertNotIn("GRANT", sql)


class NewTableTests(unittest.TestCase):
    """The twelve tables added in 30g: targets, migration, preflight and publishing."""

    TYPES = {"TEXT": "text", "INTEGER": "integer", "NUMERIC": "numeric", "BOOLEAN": "boolean",
             "JSONB": "jsonb", "TIMESTAMP": "timestamp without time zone",
             "TIMESTAMPTZ": "timestamp with time zone"}

    def test_targets_and_scopes(self):
        self.assertEqual(len(NEW_TABLES), 8)
        for retired in ("app_team_round_stats", "app_team_round_ratings",
                        "app_team_round_splits", "app_team_shot_zone_stats"):
            with self.assertRaises(ValueError):
                target_name(retired)
        self.assertEqual(target_name("app_standings_stats"), "app_standings_stats")
        self.assertEqual(target_name("app_player_rapm"), "app_player_rapm")
        for name in NEW_TABLES:
            self.assertEqual(scope(name, "E", "E2026"), ("E", "E2026"))
            self.assertEqual(predicate(name), "competition_code = %s AND season_code = %s")
            self.assertEqual(publish._relation(name, "public").strings,
                             ("public", target_name(name)))
            self.assertEqual(publish._relation(name, "gold").strings, ("gold", name))

    def test_the_migration_file_still_creates_every_current_table(self):
        # The file also created the retired tables; it stays the record of feature 30g.
        path = Path(__file__).resolve().parents[1] / "migrations" / "30g_new_tables.sql"
        text = path.read_text(encoding="utf-8")
        for statement in migration_sql().split("\n\n"):
            if statement.startswith("CREATE TABLE"):
                self.assertIn(statement, text)
        self.assertIn("main.py --print-migration; review", migration_sql())

    def test_the_ddl_creates_every_new_table_with_its_columns_and_key(self):
        ddl = migration_sql()
        self.assertTrue(ddl.startswith("-- Neon migration for feature 30g"))
        self.assertTrue(ddl.rstrip().endswith("COMMIT;"))
        self.assertEqual(ddl.count("CREATE TABLE"), 8)
        for name in NEW_TABLES:
            spec = GOLD_TABLES[name]
            self.assertIn(f"CREATE TABLE public.{target_name(name)} (", ddl)
            self.assertIn(f"PRIMARY KEY ({', '.join(spec.key)})", ddl)
            for field in spec.fields:
                self.assertIn(f'"{field.name}" {field.kind}', ddl)
        self.assertNotIn("DROP", ddl)
        self.assertNotIn("ALTER", ddl)

    def test_preflight_reports_missing_and_accepts_the_generated_shape(self):
        for name in NEW_TABLES:
            missing = mock.MagicMock()
            missing.fetchone.return_value = (None,)
            self.assertEqual(inspect_target(missing, name),
                             [f"public.{target_name(name)}: missing table"])
            spec = GOLD_TABLES[name]
            columns = [(field.name, self.TYPES[field.kind.split()[0]],
                        "NO" if "NOT NULL" in field.kind or field.name in spec.key else "YES",
                        None) for field in spec.fields]
            present = mock.MagicMock()
            present.fetchone.return_value = (target_name(name),)
            present.fetchall.side_effect = [
                columns, [("p", f"PRIMARY KEY ({', '.join(spec.key)})")]]
            self.assertEqual(inspect_target(present, name), [], name)

    def test_a_wrong_type_in_a_new_table_is_reported(self):
        spec = GOLD_TABLES["app_player_rapm"]
        columns = [(field.name, "text" if field.name == "rapm"
                    else self.TYPES[field.kind.split()[0]],
                    "NO" if "NOT NULL" in field.kind else "YES", None)
                   for field in spec.fields]
        cursor = mock.MagicMock()
        cursor.fetchone.return_value = ("app_player_rapm",)
        cursor.fetchall.side_effect = [columns, [("p", f"PRIMARY KEY ({', '.join(spec.key)})")]]
        issues = inspect_target(cursor, "app_player_rapm")
        self.assertEqual(issues, ["public.app_player_rapm.rapm: text, expected numeric"])

    def test_print_migration_needs_no_connection(self):
        with (mock.patch("neon_publish.main.connect") as local,
              mock.patch("neon_publish.main.neon_connect") as remote,
              mock.patch("sys.stdout", new_callable=io.StringIO) as output):
            self.assertEqual(publish_main(["--print-migration"]), 0)
        self.assertEqual(output.getvalue(), migration_sql())
        local.assert_not_called()
        remote.assert_not_called()

    def test_quality_runs_for_the_new_tables_before_a_live_publish(self):
        local = mock.MagicMock()
        local.cursor.return_value.__enter__.return_value.fetchone.return_value = (1,)
        with (mock.patch("neon_publish.main.connect", return_value=local),
              mock.patch("neon_publish.main.gold_main", return_value=1) as quality,
              mock.patch("neon_publish.main.neon_connect") as remote,
              mock.patch("sys.stderr", new_callable=io.StringIO)):
            self.assertEqual(publish_main(["-sc", "E2026", "-tb", "app_player_rapm",
                                           "app_lineup_ratings"]), 1)
        self.assertEqual(quality.call_args.args[0],
                         ["-sc", "E2026", "-tb", "app_player_rapm", "app_lineup_ratings",
                          "--quality-only"])
        remote.assert_not_called()

    def test_a_publish_of_new_tables_replaces_their_season_slice(self):
        names = ("app_standings_stats", "app_player_rapm")
        before = {"app_standings_stats": None, "app_player_rapm": 10}
        after = {"app_standings_stats": 1874, "app_player_rapm": 560}
        neon = FakeNeon(before)
        spools = {name: io.BytesIO(b"row\n") for name in names}

        def replace(cursor, name, *_):
            cursor.counts[name] = after[name]

        with (mock.patch.object(publish, "preflight", return_value={}),
              mock.patch.object(publish, "_remote_state", return_value=(before, {})),
              mock.patch.object(publish, "_snapshot", return_value=(after, spools, {})),
              mock.patch.object(publish, "_replace", side_effect=replace),
              mock.patch.object(publish, "_count", side_effect=lambda cursor, name, *_:
                                cursor.counts[name])):
            result = publish.publish_season(None, neon, "euroleague", "E2026", names,
                                            log=lambda _: None)
        self.assertEqual(result, {"app_standings_stats": (None, 1874),
                                  "app_player_rapm": (10, 560)})
        self.assertEqual(neon.commits, 1)

    def test_delete_and_copy_target_the_public_table_and_the_season(self):
        cursor = mock.MagicMock()
        cursor.connection = mock.MagicMock()
        with mock.patch("neon_publish.publish.sql.Composed.as_string",
                        return_value="COPY"):
            publish._replace(cursor, "app_player_rapm", "E", "E2026", io.BytesIO(), None)
        self.assertEqual(cursor.execute.call_args.args[1], ["E", "E2026"])
        cursor.copy_expert.assert_called_once()


class NullabilityTests(unittest.TestCase):
    TYPES = {"TEXT": "text", "INTEGER": "integer", "NUMERIC": "numeric", "BOOLEAN": "boolean",
             "JSONB": "jsonb", "TIMESTAMP": "timestamp without time zone",
             "TIMESTAMPTZ": "timestamp with time zone"}

    def inspect(self, name, nullable_overrides=()):
        spec = GOLD_TABLES[name]
        columns = [(field.name, self.TYPES[field.kind.split()[0]],
                    dict(nullable_overrides).get(
                        field.name, "NO" if "NOT NULL" in field.kind else "YES"), None)
                   for field in spec.fields]
        cursor = mock.MagicMock()
        cursor.fetchone.return_value = (f"app_{name}",)
        cursor.fetchall.side_effect = [columns,
                                       [("p", f"PRIMARY KEY ({', '.join(spec.key)})")]]
        return inspect_target(cursor, name)

    def test_neon_not_null_on_a_nullable_gold_field_is_reported(self):
        issues = self.inspect("app_players", {"name": "NO"})
        self.assertEqual(issues, ["public.app_players.name: NOT NULL in Neon but nullable in Gold"])

    def test_both_directions_on_one_table_are_reported(self):
        issues = self.inspect("app_players", {"name": "NO", "seasons_played": "YES"})
        self.assertEqual(len(issues), 2)
        self.assertIn("public.app_players.seasons_played: expected NOT NULL", issues)
        self.assertIn("public.app_players.name: NOT NULL in Neon but nullable in Gold", issues)

    def test_not_null_neon_columns_for_required_gold_fields_and_keys_are_accepted(self):
        for name in ("app_players", "app_games", "app_play_by_play"):
            self.assertEqual(self.inspect(name), [], name)


class PreviewOfIncompatibleTargetsTests(unittest.TestCase):
    def state(self, name, issues, **fakes):
        cursor = mock.MagicMock()
        with (mock.patch.object(publish, "_count", return_value=7) as count,
              mock.patch.object(publish, "game_rows", return_value={1: (3, None)}) as rows,
              mock.patch.object(publish, "game_checksums", return_value={1: (3, "x")}) as sums):
            result = publish._remote_state(cursor, "E", "E2025", (name,),
                                           {name: issues} if issues else {})
        return result, count, rows, sums

    @staticmethod
    def missing(target, column):
        return f"public.{target}: missing column {column} TEXT NOT NULL"

    def test_missing_scope_column_makes_counts_and_games_unavailable_without_queries(self):
        for column in ("competition_code", "season_code"):
            (counts, sums), count, rows, checks = self.state(
                "app_play_by_play", [self.missing("app_play_by_play", column)])
            self.assertEqual((counts, sums), ({"app_play_by_play": None}, {"app_play_by_play": {}}))
            for fake in (count, rows, checks):
                fake.assert_not_called()

    def test_missing_game_code_keeps_the_count_but_not_the_game_rows(self):
        (counts, sums), count, rows, checks = self.state(
            "app_shots", [self.missing("app_shots", "game_code")])
        self.assertEqual((counts, sums), ({"app_shots": 7}, {"app_shots": {}}))
        count.assert_called_once()
        rows.assert_not_called()
        checks.assert_not_called()

    def test_season_column_is_not_needed_for_a_competition_wide_table(self):
        (counts, _), count, _, _ = self.state(
            "app_players", [self.missing("app_players", "season_code")])
        self.assertEqual(counts, {"app_players": 7})
        count.assert_called_once()
        (counts, _), count, _, _ = self.state(
            "app_players", [self.missing("app_players", "competition_code")])
        self.assertEqual(counts, {"app_players": None})
        count.assert_not_called()

    def test_other_problems_and_clean_tables_are_queried_as_before(self):
        (counts, sums), count, rows, checks = self.state(
            "app_play_by_play", ["public.app_play_by_play: extra required column"])
        self.assertEqual((counts, sums), ({"app_play_by_play": 7},
                                          {"app_play_by_play": {1: (3, None)}}))
        checks.assert_not_called()
        (counts, sums), _, rows, checks = self.state("app_play_by_play", [])
        self.assertEqual(sums, {"app_play_by_play": {1: (3, "x")}})
        rows.assert_not_called()
        (counts, sums), _, _, _ = self.state(
            "app_games", ["public.app_games: missing table"])
        self.assertEqual(counts, {"app_games": None})

    @staticmethod
    def wrong_type(target, column):
        return f"public.{target}.{column}: integer, expected TEXT"

    def test_wrong_scope_column_type_makes_counts_unavailable_without_queries(self):
        for column in ("competition_code", "season_code"):
            (counts, sums), count, rows, checks = self.state(
                "app_play_by_play", [self.wrong_type("app_play_by_play", column)])
            self.assertEqual((counts, sums), ({"app_play_by_play": None}, {"app_play_by_play": {}}))
            for fake in (count, rows, checks):
                fake.assert_not_called()

    def test_wrong_type_on_other_columns_and_global_season_column_still_query(self):
        (counts, _), count, _, _ = self.state(
            "app_play_by_play", [self.wrong_type("app_play_by_play", "quarter"),
                             "public.app_play_by_play.season_code: expected NOT NULL"])
        self.assertEqual(counts, {"app_play_by_play": 7})
        (counts, _), count, _, _ = self.state(
            "app_players", [self.wrong_type("app_players", "season_code")])
        self.assertEqual(counts, {"app_players": 7})
        (counts, _), count, _, _ = self.state(
            "app_players", [self.wrong_type("app_players", "competition_code")])
        self.assertEqual(counts, {"app_players": None})
        count.assert_not_called()

    def test_cli_labels_an_unavailable_count(self):
        from neon_publish import main as cli
        with (mock.patch.object(cli, "connect"), mock.patch.object(cli, "neon_connect"),
              mock.patch.object(cli, "publish_season",
                                return_value={"app_play_by_play": (None, 5), "app_shots": (2, 5)}),
              mock.patch("sys.stdout", new_callable=io.StringIO) as out):
            self.assertEqual(cli.main(["-sc", "E2025", "--dry-run"]), 0)
        self.assertIn("unavailable -> 5 rows", out.getvalue())
        self.assertNotIn("missing", out.getvalue())

    def run_publish(self, dry_run):
        issues = {"app_play_by_play": [self.missing("app_play_by_play", "competition_code"),
                                   self.missing("app_play_by_play", "game_code")]}
        neon = FakeNeon({})
        plans = {"app_play_by_play": ([1], [], 1)}
        with (mock.patch.object(publish, "preflight", return_value=issues),
              mock.patch.object(publish, "_snapshot",
                                return_value=({"app_play_by_play": 5},
                                              {"app_play_by_play": io.BytesIO(b"row\n")}, plans)),
              mock.patch.object(publish, "_count",
                                side_effect=AssertionError("queried an incompatible table")),
              mock.patch.object(publish, "_replace") as replace):
            try:
                return publish.publish_season(None, neon, "euroleague", "E2025",
                                              ("app_play_by_play",), dry_run=dry_run,
                                              log=lambda _: None), replace
            except Exception as error:
                return error, replace

    def test_dry_run_reports_instead_of_failing_and_real_publish_still_refuses(self):
        result, replace = self.run_publish(dry_run=True)
        self.assertEqual(result, {"app_play_by_play": (None, 5)})
        replace.assert_not_called()
        error, replace = self.run_publish(dry_run=False)
        self.assertIsInstance(error, ValueError)
        self.assertIn("preflight failed", str(error))
        replace.assert_not_called()


class FakeNeon:
    def __init__(self, counts):
        self.counts = dict(counts)
        self.original = dict(counts)
        self.commits = 0
        self.rollbacks = 0
        self.sessions = []

    def set_session(self, **options):
        self.sessions.append(options)

    def __enter__(self):
        return self

    def __exit__(self, kind, *_):
        if kind is None:
            self.commits += 1
        else:
            self.counts = self.original.copy()
            self.rollbacks += 1
        return False

    def cursor(self):
        return nullcontext(self)

    def execute(self, *_):
        pass


class TransactionTests(unittest.TestCase):
    def test_removed_game_deletes_without_copy(self):
        cursor = mock.MagicMock()
        publish._replace(cursor, "app_play_by_play", "E", "E2025", io.BytesIO(),
                         ([], [42], 0))
        cursor.copy_expert.assert_not_called()
        self.assertEqual(cursor.execute.call_args.args[1], ("E", "E2025", [42]))

    def run_publish(self, before, after, *, dry_run=False, allow_shrink=False,
                    issues=None, fail_after=None):
        neon = FakeNeon(before)
        names = tuple(after)
        spools = {name: io.BytesIO(b"row\n") for name in names}

        def replace(cursor, name, *_):
            cursor.counts[name] = after[name]
            if name == fail_after:
                raise RuntimeError("COPY failed")

        with (mock.patch.object(publish, "preflight", return_value=issues or {}),
              mock.patch.object(publish, "_remote_state", return_value=(before, {})),
              mock.patch.object(publish, "_snapshot", return_value=(after, spools, {})),
              mock.patch.object(publish, "_replace", side_effect=replace) as copied,
              mock.patch.object(publish, "_count", side_effect=lambda cursor, name, *_:
                                cursor.counts[name])):
            try:
                result = publish.publish_season(None, neon, "euroleague", "E2025", names,
                                                dry_run=dry_run, allow_shrink=allow_shrink,
                                                log=lambda _: None)
            except Exception as error:
                result = error
        return neon, result, copied.call_count

    def test_first_publish_and_rerun(self):
        for before in ({"app_games": None, "app_players": None},
                       {"app_games": 10, "app_players": 4}):
            neon, result, copies = self.run_publish(before, {"app_games": 10, "app_players": 4})
            self.assertEqual(result, {name: (before[name], count)
                                      for name, count in {"app_games": 10, "app_players": 4}.items()})
            self.assertEqual((neon.commits, copies), (1, 2))

    def test_shrink_refusal_and_explicit_override(self):
        neon, result, copies = self.run_publish({"app_games": 100}, {"app_games": 0})
        self.assertIsInstance(result, ValueError)
        self.assertEqual((neon.rollbacks, copies), (1, 0))
        neon, result, copies = self.run_publish({"app_games": 100}, {"app_games": 0},
                                                allow_shrink=True)
        self.assertEqual((neon.commits, copies), (1, 1))

    def test_dry_run_never_copies_even_with_schema_and_shrink_problems(self):
        neon, result, copies = self.run_publish({"app_games": 100}, {"app_games": 0},
                                                dry_run=True, issues={"app_games": ["missing column"]})
        self.assertEqual(result, {"app_games": (100, 0)})
        self.assertEqual(copies, 0)
        self.assertEqual(neon.sessions, [{"readonly": True}, {"readonly": False}])

    def test_schema_problem_fails_before_mutation(self):
        neon, result, copies = self.run_publish({"app_games": 10}, {"app_games": 10},
                                                issues={"app_games": ["missing column"]})
        self.assertIsInstance(result, ValueError)
        self.assertEqual((neon.rollbacks, copies), (1, 0))

    def test_an_empty_scope_publishes_cleanly(self):
        for before in (None, 0):
            neon, result, copies = self.run_publish({"app_game_stat_gaps": before},
                                                    {"app_game_stat_gaps": 0})
            self.assertEqual(result, {"app_game_stat_gaps": (before, 0)})
            self.assertEqual((neon.commits, neon.rollbacks, copies), (1, 0, 1))

    def test_failed_second_copy_rolls_back_first(self):
        neon, result, copies = self.run_publish({"app_games": 10, "app_players": 4},
                                                {"app_games": 11, "app_players": 5},
                                                fail_after="app_players")
        self.assertIsInstance(result, RuntimeError)
        self.assertEqual((neon.rollbacks, copies), (1, 2))
        self.assertEqual(neon.counts, {"app_games": 10, "app_players": 4})


class GameAdvancedTests(unittest.TestCase):
    """The two per-game advanced tables added in 30h."""

    def test_targets_scope_and_migration_file(self):
        self.assertEqual([target_name(name) for name in GAME_TABLES],
                         ["app_game_player_advanced", "app_game_team_advanced"])
        for name in GAME_TABLES:
            self.assertEqual(scope(name, "E", "E2026"), ("E", "E2026"))
        path = Path(__file__).resolve().parents[1] / "migrations" / "30h_game_advanced.sql"
        ddl = migration_sql(GAME_TABLES, "30h")
        self.assertEqual(path.read_text(encoding="utf-8"), ddl)
        self.assertEqual(ddl.count("CREATE TABLE"), 2)
        self.assertIn("PRIMARY KEY (competition_code, season_code, game_code, side, person_key)", ddl)
        self.assertIn("PRIMARY KEY (competition_code, season_code, game_code, side)", ddl)
        self.assertIn("main.py --print-migration 30h; review", ddl)
        self.assertNotIn("GRANT", ddl)

    def test_print_migration_selects_the_feature(self):
        with (mock.patch("neon_publish.main.connect") as local,
              mock.patch("sys.stdout", new_callable=io.StringIO) as output):
            self.assertEqual(publish_main(["--print-migration", "30h"]), 0)
        self.assertEqual(output.getvalue(), migration_sql(GAME_TABLES, "30h"))
        local.assert_not_called()


class GamePbpTests(unittest.TestCase):
    """The per-game play-by-play tables added in 30i, less the retired shot zones."""

    def test_targets_scope_and_migration_file(self):
        self.assertEqual([target_name(name) for name in GAME_PBP_TABLES],
                         ["app_game_team_possessions", "app_game_team_score_flow",
                          "app_game_team_shot_splits"])
        for name in GAME_PBP_TABLES:
            self.assertEqual(scope(name, "E", "E2026"), ("E", "E2026"))
        path = Path(__file__).resolve().parents[1] / "migrations" / "30i_game_play_by_play.sql"
        text = path.read_text(encoding="utf-8")
        ddl = migration_sql(GAME_PBP_TABLES, "30i")
        for statement in ddl.split("\n\n"):
            if statement.startswith("CREATE TABLE"):
                self.assertIn(statement, text)
        self.assertEqual(ddl.count("CREATE TABLE"), 3)
        self.assertNotIn("app_game_team_shot_zones", ddl)
        self.assertIn("CREATE TABLE public.app_game_team_shot_zones (", text)
        self.assertIn("main.py --print-migration 30i; review", ddl)
        self.assertNotIn("GRANT", ddl)

    def test_print_migration_selects_the_feature(self):
        with (mock.patch("neon_publish.main.connect") as local,
              mock.patch("sys.stdout", new_callable=io.StringIO) as output):
            self.assertEqual(publish_main(["--print-migration", "30i"]), 0)
        self.assertEqual(output.getvalue(), migration_sql(GAME_PBP_TABLES, "30i"))
        local.assert_not_called()


class GameCourtTests(unittest.TestCase):
    """The three on-court, lineup-stint and stat-gap tables added in 30j."""

    def test_targets_scope_and_migration_file(self):
        self.assertEqual([target_name(name) for name in GAME_COURT_TABLES],
                         ["app_game_player_on_court", "app_game_team_lineup_stints",
                          "app_game_stat_gaps"])
        for name in GAME_COURT_TABLES:
            self.assertEqual(scope(name, "E", "E2026"), ("E", "E2026"))
        path = Path(__file__).resolve().parents[1] / "migrations" / "30j_game_on_court_and_gaps.sql"
        ddl = migration_sql(GAME_COURT_TABLES, "30j")
        self.assertEqual(path.read_text(encoding="utf-8"), ddl)
        self.assertEqual(ddl.count("CREATE TABLE"), 3)
        self.assertIn("PRIMARY KEY (competition_code, season_code, game_code, side, person_key, "
                      "interval_ordinal)", ddl)
        self.assertIn("PRIMARY KEY (competition_code, season_code, game_code, stat_name)", ddl)
        self.assertIn("main.py --print-migration 30j; review", ddl)
        self.assertNotIn("GRANT", ddl)

    def test_print_migration_selects_the_feature(self):
        with (mock.patch("neon_publish.main.connect") as local,
              mock.patch("sys.stdout", new_callable=io.StringIO) as output):
            self.assertEqual(publish_main(["--print-migration", "30j"]), 0)
        self.assertEqual(output.getvalue(), migration_sql(GAME_COURT_TABLES, "30j"))
        local.assert_not_called()


class CliTests(unittest.TestCase):
    def test_list_tables_needs_no_connections(self):
        with (mock.patch("neon_publish.main.connect") as local,
              mock.patch("neon_publish.main.neon_connect") as remote,
              mock.patch("sys.stdout", new_callable=io.StringIO) as output):
            self.assertEqual(publish_main(["--list-tables"]), 0)
        self.assertEqual(len(output.getvalue().splitlines()), 40)
        local.assert_not_called()
        remote.assert_not_called()

    def test_missing_url_is_redacted_to_failure_class(self):
        local = mock.MagicMock()
        local.cursor.return_value.__enter__.return_value.fetchone.return_value = (1,)
        with (mock.patch("neon_publish.main.connect", return_value=local),
              mock.patch("neon_publish.main.gold_main", return_value=0),
              mock.patch("neon_publish.main.neon_connect", side_effect=RuntimeError("missing URL")),
              mock.patch("sys.stderr", new_callable=io.StringIO) as error):
            self.assertEqual(publish_main(["-sc", "E2025"]), 1)
        self.assertIn("Publish failed", error.getvalue())

    def test_quality_failure_blocks_neon_connection(self):
        local = mock.MagicMock()
        local.cursor.return_value.__enter__.return_value.fetchone.return_value = (1,)
        with (mock.patch("neon_publish.main.connect", return_value=local),
              mock.patch("neon_publish.main.gold_main", return_value=1),
              mock.patch("neon_publish.main.neon_connect") as remote,
              mock.patch("sys.stderr", new_callable=io.StringIO)):
            self.assertEqual(publish_main(["-sc", "E2025", "-tb", "app_games"]), 1)
        remote.assert_not_called()

    def test_dry_run_skips_quality_and_passes_read_only_mode(self):
        local = mock.MagicMock()
        local.cursor.return_value.__enter__.return_value.fetchone.return_value = (1,)
        remote = mock.MagicMock()
        with (mock.patch("neon_publish.main.connect", return_value=local),
              mock.patch("neon_publish.main.gold_main") as quality,
              mock.patch("neon_publish.main.neon_connect", return_value=remote),
              mock.patch("neon_publish.main.publish_season",
                         return_value={"app_games": (1, 1)}) as engine,
              mock.patch("sys.stdout", new_callable=io.StringIO)):
            self.assertEqual(publish_main(["-sc", "E2025", "-tb", "app_games",
                                           "--dry-run"]), 0)
        quality.assert_not_called()
        self.assertTrue(engine.call_args.kwargs["dry_run"])


class HistoryPipelineTests(unittest.TestCase):
    def run_history(self, flags=(), fail_at=None, changed=0, year=2026):
        args = build_parser().parse_args(["--all", *flags])
        stages = []
        facts = StageFacts()
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state.json"

            def runner(command, cwd, env, emit):
                stages.append((command, cwd, env))
                index = len(stages) - 1
                if index == fail_at:
                    return 7
                if command[1] == "main.py":
                    summary = Path(command[command.index("--summary-file") + 1])
                    summary.write_text(json.dumps({
                        "changed_resources": ["_catalog/seasons"] + [f"resource/{i}" for i in range(changed)],
                        "failed_requests": 0,
                        "kept_resources": ["kept_feed"], "behind_resources": ["behind_feed"],
                    }), encoding="utf-8")
                elif command[1] == "postgres_etl/main.py":
                    emit("Finished: 12 rows")
                    emit("Quality E2026: 1 table(s), 12 rows, 0 error(s), 1 warning(s)")
                elif "--quality-only" in command:
                    emit("Gold quality: passed")
                return 0

            with (mock.patch("pipeline.current_season_year", return_value=year),
                  mock.patch("pipeline.resolve_neon_url", side_effect=AssertionError("Neon accessed"))):
                result = refresh_history(args, mock.Mock(), state, facts, stage_runner=runner,
                                         environ={"LOCAL_MARKER": "present"})
            pending = read_state(state).get("publish_pending")
        return result, stages, facts, pending

    def test_full_fetch_rebuilds_all_layers_even_when_fetch_is_unchanged(self):
        result, stages, facts, pending = self.run_history()
        self.assertEqual(result[:2], (0, "LOCAL OK"))
        self.assertEqual([command[1] for command, _, _ in stages],
                         ["main.py", "postgres_etl/main.py", "gold_etl/main.py", "gold_etl/main.py"])
        self.assertEqual(facts.changed, 0)
        self.assertTrue(pending)
        self.assertIn("--refresh-current", stages[0][0])
        for command, _, env in stages[1:]:
            self.assertEqual(command[command.index("-sc") + 1], "all")
            self.assertEqual(env["LOCAL_MARKER"], "present")
        self.assertEqual(facts.gold_status, "built and quality checked")
        self.assertIn("--quality-only", stages[-1][0])
        self.assertEqual(facts.publish_lines, [])

    def test_cached_mode_skips_api_and_never_publishes(self):
        result, stages, facts, pending = self.run_history(["--skip-fetch"])
        self.assertEqual(result[0], 0)
        self.assertEqual([command[1] for command, _, _ in stages],
                         ["postgres_etl/main.py", "gold_etl/main.py", "gold_etl/main.py"])
        self.assertIsNone(facts.changed)
        self.assertTrue(pending)
        summary = "\n".join(build_summary("all", result[1], facts, 1, "log"))
        self.assertIn("Fetch:    not run", summary)
        self.assertIn("Publish:  skipped", summary)
        self.assertIn("quality 0 error(s), 1 warning(s)", summary)

    def test_year_range_and_fetch_options_are_forwarded(self):
        _, stages, _, _ = self.run_history(["--request-interval", "3", "--hot-hours", "72"], year=2027)
        command = stages[0][0]
        self.assertEqual(command[command.index("-sc") + 1], "2000-2027")
        self.assertEqual(command[command.index("--request-interval") + 1], "3.0")
        self.assertEqual(command[command.index("--hot-hours") + 1], "72.0")
        self.assertEqual(stages[0][1].name, "api_requests")

    def test_fetch_metadata_remains_visible(self):
        result, _, facts, _ = self.run_history(changed=2)
        self.assertEqual(facts.changed, 2)
        self.assertEqual(facts.failed_requests, 0)
        summary = "\n".join(build_summary("all", result[1], facts, 1, "log"))
        self.assertIn("kept_feed", summary)
        self.assertIn("behind_feed", summary)

    def test_each_failed_stage_stops_later_stages(self):
        for index, title in enumerate(("Fetch", "Load", "Gold build", "Gold quality")):
            with self.subTest(stage=title):
                result, stages, facts, pending = self.run_history(fail_at=index)
                self.assertEqual(result[0], 7)
                self.assertIn(f"FAILED at {title}", result[1])
                self.assertEqual(len(stages), index + 1)
                self.assertEqual(pending, None if index == 0 else True)
                self.assertEqual(facts.publish_lines, [])

    def test_main_routes_all_to_local_history_and_uses_current_pending_state(self):
        import pipeline
        with tempfile.TemporaryDirectory() as directory:
            with (mock.patch.object(pipeline, "current_season_year", return_value=2027),
                  mock.patch.object(pipeline, "log_directory", return_value=Path(directory)),
                  mock.patch.object(pipeline, "refresh_history", return_value=(0, "LOCAL OK", None)) as history,
                  mock.patch.object(pipeline, "refresh") as single,
                  mock.patch("sys.stdout", new_callable=io.StringIO)):
                self.assertEqual(pipeline.main(["--all", "--skip-fetch"]), 0)
            single.assert_not_called()
            self.assertTrue(history.call_args.args[0].skip_fetch)
            self.assertEqual(history.call_args.args[2].name, "pipeline_euroleague_E2027.json")

    def test_conflicting_flags_fail_before_any_stage_or_log(self):
        import pipeline
        for flags in (["-sc", "E2025"], ["--dry-run-publish"], ["--allow-shrink"]):
            with (self.subTest(flags=flags), mock.patch.object(pipeline, "refresh_history") as history,
                  mock.patch.object(pipeline, "log_directory") as logs,
                  mock.patch("sys.stderr", new_callable=io.StringIO), self.assertRaises(SystemExit) as error):
                pipeline.main(["--all", *flags])
            self.assertEqual(error.exception.code, 2)
            history.assert_not_called()
            logs.assert_not_called()


class PipelineTests(unittest.TestCase):
    class Log:
        def line(self, *_):
            pass

    def run_refresh(self, flags, outcomes=None, initial_pending=False,
                    fetch=False, changed=0):
        stages = []
        outcomes = outcomes or {}
        with tempfile.TemporaryDirectory() as root:
            state = Path(root) / "state.json"
            if initial_pending:
                state.write_text('{"publish_pending": true}')
            def runner(command, cwd, env, emit):
                stage = command[1]
                stages.append((stage, command, env))
                if stage == "main.py":
                    path = Path(command[command.index("--summary-file") + 1])
                    path.write_text(json.dumps({"changed_resources":
                                               [f"resource/{i}" for i in range(changed)],
                                               "failed_requests": 0}), encoding="utf-8")
                if stage == "neon_publish/main.py" and outcomes.get(stage, 0) == 0:
                    emit("Season E2025 checked" if "--dry-run" in command
                         else "Season E2025 committed")
                return outcomes.get(stage + (" quality" if "--quality-only" in command else ""),
                                    outcomes.get(stage, 0))
            args = build_parser().parse_args(([] if fetch else ["--skip-fetch"]) + flags)
            facts = StageFacts()
            result = refresh(args, "E2025", self.Log(), state, facts,
                             stage_runner=runner, environ={"NEON_DATABASE_URL":
                             "postgresql://user:password@example.test/db"}, interactive=False)
            pending = read_state(state).get("publish_pending")
            summary = build_summary("E2025", result[1], facts, 1, "log")
        return result, pending, stages, summary

    def test_success_clears_pending_after_publish(self):
        result, pending, stages, summary = self.run_refresh([])
        self.assertEqual((result[0], pending), (0, False))
        self.assertEqual([x[0] for x in stages], ["postgres_etl/main.py",
                         "gold_etl/main.py", "gold_etl/main.py", "neon_publish/main.py"])
        self.assertIn("Publish:  committed", summary)

    def test_failed_stage_or_dry_run_retains_pending(self):
        for outcomes in ({"postgres_etl/main.py": 1}, {"gold_etl/main.py": 1},
                         {"gold_etl/main.py quality": 1}, {"neon_publish/main.py": 1}):
            result, pending, _, _ = self.run_refresh([], outcomes)
            self.assertNotEqual(result[0], 0)
            self.assertTrue(pending)
        result, pending, stages, summary = self.run_refresh(["--dry-run-publish"])
        self.assertEqual(result[0], 0)
        self.assertTrue(pending)
        self.assertIn("--dry-run", stages[-1][1])
        self.assertIn("dry run", "\n".join(summary))

    def test_allow_shrink_forwarded_only_when_requested(self):
        _, _, stages, _ = self.run_refresh([])
        self.assertNotIn("--allow-shrink", stages[-1][1])
        _, _, stages, _ = self.run_refresh(["--allow-shrink"])
        self.assertIn("--allow-shrink", stages[-1][1])

    def test_unchanged_fetch_skips_unless_pending_or_forced(self):
        result, pending, stages, _ = self.run_refresh([], fetch=True)
        self.assertEqual(result[1], "NOTHING TO DO")
        self.assertEqual([stage for stage, _, _ in stages], ["main.py"])
        self.assertIsNone(pending)
        result, pending, stages, _ = self.run_refresh([], fetch=True,
                                                       initial_pending=True)
        self.assertEqual(result[0], 0)
        self.assertFalse(pending)
        self.assertEqual(stages[-1][0], "neon_publish/main.py")
        result, pending, stages, _ = self.run_refresh(["--force"], fetch=True)
        self.assertEqual(result[0], 0)
        self.assertEqual(stages[-1][0], "neon_publish/main.py")

    def test_changed_fetch_retains_pending_on_load_failure(self):
        result, pending, stages, _ = self.run_refresh([], fetch=True, changed=2,
                                                       outcomes={"postgres_etl/main.py": 1})
        self.assertNotEqual(result[0], 0)
        self.assertTrue(pending)
        self.assertEqual([stage for stage, _, _ in stages],
                         ["main.py", "postgres_etl/main.py"])

    def test_kept_feed_is_visible_in_refresh_summary(self):
        facts = StageFacts(changed=0, failed_requests=0,
                           kept=["E2026/v3/season_stats/players_scoring_all_accumulated"])
        summary = "\n".join(build_summary("E2026", "NOTHING TO DO", facts, 1, "log"))
        self.assertIn("1 stats feed(s) kept", summary)
        self.assertIn("players_scoring_all_accumulated", summary)
        self.assertNotIn("behind the v2 games", summary)

    def test_feeds_behind_the_v2_games_are_visible_only_when_there_are_any(self):
        facts = StageFacts(changed=0, failed_requests=0,
                           behind=["E2026/v3/season_stats/teams_traditional_RS_accumulated"])
        summary = "\n".join(build_summary("E2026", "NOTHING TO DO", facts, 1, "log"))
        self.assertIn("1 stats feed(s) still behind the v2 games", summary)
        self.assertIn("teams_traditional_RS_accumulated", summary)
        self.assertNotIn("kept from an earlier fetch", summary)

    def test_neon_prompt_waits_until_gold_quality_passes(self):
        args = build_parser().parse_args(["--skip-fetch"])
        with tempfile.TemporaryDirectory() as root:
            state = Path(root) / "state.json"
            stages = []
            prompts = []
            def runner(command, cwd, env, emit):
                stages.append(command[1])
                return 1 if command[1] == "gold_etl/main.py" and "--quality-only" in command else 0
            result = refresh(args, "E2025", self.Log(), state, StageFacts(),
                             stage_runner=runner, environ={}, interactive=True,
                             dotenv_path=Path(root) / ".env",
                             prompt=lambda _: prompts.append(True))
        self.assertIn("Gold quality", result[1])
        self.assertEqual(prompts, [])
        self.assertNotIn("neon_publish/main.py", stages)

    def test_unattended_run_without_neon_url_fails_without_prompting(self):
        args = build_parser().parse_args(["--skip-fetch"])
        with tempfile.TemporaryDirectory() as root:
            state = Path(root) / "state.json"
            stages = []
            def runner(command, cwd, env, emit):
                stages.append(command[1])
                return 0
            result = refresh(args, "E2025", self.Log(), state, StageFacts(),
                             stage_runner=runner, environ={}, interactive=False,
                             dotenv_path=Path(root) / ".env",
                             prompt=lambda _: self.fail("prompted without a console"))
            pending = read_state(state).get("publish_pending")
        self.assertEqual(result[:2], (1, "FAILED at Publish (missing Neon URL)"))
        self.assertNotIn("neon_publish/main.py", stages)
        self.assertTrue(pending)

    def test_publish_output_redacts_url_and_password(self):
        url = "postgresql://user:verysecret@example.test/db"
        cleaned = redactor(url)(f"failed to connect {url}; password verysecret")
        self.assertNotIn("verysecret", cleaned)
        self.assertNotIn(url, cleaned)

    def test_refresh_redacts_publish_stage_output(self):
        url = "postgresql://user:verysecret@example.test/db"
        lines = []
        log = mock.Mock()
        log.line.side_effect = lines.append
        args = build_parser().parse_args(["--skip-fetch"])
        with tempfile.TemporaryDirectory() as root:
            def runner(command, cwd, env, emit):
                if command[1] == "neon_publish/main.py":
                    emit(f"failed to connect {url}; password verysecret")
                    return 1
                return 0
            result = refresh(args, "E2025", log, Path(root) / "state.json",
                             StageFacts(), stage_runner=runner,
                             environ={"NEON_DATABASE_URL": url}, interactive=False)
        self.assertNotEqual(result[0], 0)
        self.assertNotIn("verysecret", "\n".join(lines))


if __name__ == "__main__":
    unittest.main()
