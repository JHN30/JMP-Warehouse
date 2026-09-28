"""Gold-to-Neon contract, transaction, CLI, and refresh regression tests."""

import io
import json
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest import mock

from gold_etl.schema import DERIVED_NAMES, GOLD_TABLES, ROUND_NAMES, SOURCE_NAMES
from neon_publish import publish
from neon_publish.contract import (APP_TABLES, GLOBAL_TABLES, inspect_target,
                                   predicate, scope, target_name)
from neon_publish.main import main as publish_main
from pipeline import StageFacts, build_parser, build_summary, read_state, redactor, refresh


class ContractTests(unittest.TestCase):
    def test_every_gold_table_has_a_fixed_target_and_scope(self):
        self.assertEqual(APP_TABLES, SOURCE_NAMES + DERIVED_NAMES)
        self.assertEqual(len(APP_TABLES), 26)
        self.assertEqual(len({target_name(name) for name in APP_TABLES}), 26)
        self.assertEqual(len(GLOBAL_TABLES), 5)
        # Local-only round tables are Gold tables but never published.
        self.assertEqual(set(APP_TABLES), set(GOLD_TABLES) - set(ROUND_NAMES))
        for name in APP_TABLES:
            self.assertEqual(target_name(name), name if name.startswith("app_")
                             else "app_" + name)
            self.assertEqual(scope(name, "E", "E2025"),
                             ("E",) if name in GLOBAL_TABLES else ("E", "E2025"))
            self.assertEqual(predicate(name), "competition_code = %s" if name in GLOBAL_TABLES
                             else "competition_code = %s AND season_code = %s")

    def test_shrink_and_game_diff(self):
        self.assertEqual(publish.shrink_problems({"games": 80}, {"games": 100}),
                         ["app_games: 100 -> 80 rows"])
        self.assertEqual(publish.shrink_problems({"games": 95}, {"games": 100}), [])
        self.assertEqual(publish.changed_games({1: (10, "a"), 2: (8, "b")},
                                               {1: (10, "a"), 3: (2, "c")}), ([2], [3]))

    def test_preflight_reports_missing_compatible_and_incompatible(self):
        missing = mock.MagicMock()
        missing.fetchone.return_value = (None,)
        self.assertEqual(inspect_target(missing, "games"),
                         ["public.app_games: missing table"])
        self.assertFalse(any("ALTER" in str(call) for call in missing.execute.call_args_list))

        spec = GOLD_TABLES["games"]
        columns = [(field.name, {"TEXT": "text", "INTEGER": "integer",
                                 "BOOLEAN": "boolean", "TIMESTAMP": "timestamp without time zone",
                                 "TIMESTAMPTZ": "timestamp with time zone"}[field.kind.split()[0]],
                    "NO" if "NOT NULL" in field.kind else "YES", None)
                   for field in spec.fields]
        key = ", ".join(spec.key)
        compatible = mock.MagicMock()
        compatible.fetchone.return_value = ("app_games",)
        compatible.fetchall.side_effect = [columns, [("p", f"PRIMARY KEY ({key})")]]
        self.assertEqual(inspect_target(compatible, "games"), [])
        incompatible = mock.MagicMock()
        incompatible.fetchone.return_value = ("app_games",)
        incompatible.fetchall.side_effect = [columns[:-1] + [("extra", "text", "NO", None)],
                                             [("p", "PRIMARY KEY (wrong)")]]
        issues = inspect_target(incompatible, "games")
        self.assertTrue(any("missing column" in issue for issue in issues))
        self.assertTrue(any("extra required column" in issue for issue in issues))
        self.assertTrue(any("primary key differs" in issue for issue in issues))


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
        for name in ("app_players", "games", "play_by_play"):
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
                "play_by_play", [self.missing("app_play_by_play", column)])
            self.assertEqual((counts, sums), ({"play_by_play": None}, {"play_by_play": {}}))
            for fake in (count, rows, checks):
                fake.assert_not_called()

    def test_missing_game_code_keeps_the_count_but_not_the_game_rows(self):
        (counts, sums), count, rows, checks = self.state(
            "shots", [self.missing("app_shots", "game_code")])
        self.assertEqual((counts, sums), ({"shots": 7}, {"shots": {}}))
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
            "play_by_play", ["public.app_play_by_play: extra required column"])
        self.assertEqual((counts, sums), ({"play_by_play": 7},
                                          {"play_by_play": {1: (3, None)}}))
        checks.assert_not_called()
        (counts, sums), _, rows, checks = self.state("play_by_play", [])
        self.assertEqual(sums, {"play_by_play": {1: (3, "x")}})
        rows.assert_not_called()
        (counts, sums), _, _, _ = self.state(
            "games", ["public.app_games: missing table"])
        self.assertEqual(counts, {"games": None})

    @staticmethod
    def wrong_type(target, column):
        return f"public.{target}.{column}: integer, expected TEXT"

    def test_wrong_scope_column_type_makes_counts_unavailable_without_queries(self):
        for column in ("competition_code", "season_code"):
            (counts, sums), count, rows, checks = self.state(
                "play_by_play", [self.wrong_type("app_play_by_play", column)])
            self.assertEqual((counts, sums), ({"play_by_play": None}, {"play_by_play": {}}))
            for fake in (count, rows, checks):
                fake.assert_not_called()

    def test_wrong_type_on_other_columns_and_global_season_column_still_query(self):
        (counts, _), count, _, _ = self.state(
            "play_by_play", [self.wrong_type("app_play_by_play", "quarter"),
                             "public.app_play_by_play.season_code: expected NOT NULL"])
        self.assertEqual(counts, {"play_by_play": 7})
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
                                return_value={"play_by_play": (None, 5), "shots": (2, 5)}),
              mock.patch("sys.stdout", new_callable=io.StringIO) as out):
            self.assertEqual(cli.main(["-sc", "E2025", "--dry-run"]), 0)
        self.assertIn("unavailable -> 5 rows", out.getvalue())
        self.assertNotIn("missing", out.getvalue())

    def run_publish(self, dry_run):
        issues = {"play_by_play": [self.missing("app_play_by_play", "competition_code"),
                                   self.missing("app_play_by_play", "game_code")]}
        neon = FakeNeon({})
        plans = {"play_by_play": ([1], [], 1)}
        with (mock.patch.object(publish, "preflight", return_value=issues),
              mock.patch.object(publish, "_snapshot",
                                return_value=({"play_by_play": 5},
                                              {"play_by_play": io.BytesIO(b"row\n")}, plans)),
              mock.patch.object(publish, "_count",
                                side_effect=AssertionError("queried an incompatible table")),
              mock.patch.object(publish, "_replace") as replace):
            try:
                return publish.publish_season(None, neon, "euroleague", "E2025",
                                              ("play_by_play",), dry_run=dry_run,
                                              log=lambda _: None), replace
            except Exception as error:
                return error, replace

    def test_dry_run_reports_instead_of_failing_and_real_publish_still_refuses(self):
        result, replace = self.run_publish(dry_run=True)
        self.assertEqual(result, {"play_by_play": (None, 5)})
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
        publish._replace(cursor, "play_by_play", "E", "E2025", io.BytesIO(),
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
        for before in ({"games": None, "app_players": None},
                       {"games": 10, "app_players": 4}):
            neon, result, copies = self.run_publish(before, {"games": 10, "app_players": 4})
            self.assertEqual(result, {name: (before[name], count)
                                      for name, count in {"games": 10, "app_players": 4}.items()})
            self.assertEqual((neon.commits, copies), (1, 2))

    def test_shrink_refusal_and_explicit_override(self):
        neon, result, copies = self.run_publish({"games": 100}, {"games": 0})
        self.assertIsInstance(result, ValueError)
        self.assertEqual((neon.rollbacks, copies), (1, 0))
        neon, result, copies = self.run_publish({"games": 100}, {"games": 0},
                                                allow_shrink=True)
        self.assertEqual((neon.commits, copies), (1, 1))

    def test_dry_run_never_copies_even_with_schema_and_shrink_problems(self):
        neon, result, copies = self.run_publish({"games": 100}, {"games": 0},
                                                dry_run=True, issues={"games": ["missing column"]})
        self.assertEqual(result, {"games": (100, 0)})
        self.assertEqual(copies, 0)
        self.assertEqual(neon.sessions, [{"readonly": True}, {"readonly": False}])

    def test_schema_problem_fails_before_mutation(self):
        neon, result, copies = self.run_publish({"games": 10}, {"games": 10},
                                                issues={"games": ["missing column"]})
        self.assertIsInstance(result, ValueError)
        self.assertEqual((neon.rollbacks, copies), (1, 0))

    def test_failed_second_copy_rolls_back_first(self):
        neon, result, copies = self.run_publish({"games": 10, "app_players": 4},
                                                {"games": 11, "app_players": 5},
                                                fail_after="app_players")
        self.assertIsInstance(result, RuntimeError)
        self.assertEqual((neon.rollbacks, copies), (1, 2))
        self.assertEqual(neon.counts, {"games": 10, "app_players": 4})


class CliTests(unittest.TestCase):
    def test_list_tables_needs_no_connections(self):
        with (mock.patch("neon_publish.main.connect") as local,
              mock.patch("neon_publish.main.neon_connect") as remote,
              mock.patch("sys.stdout", new_callable=io.StringIO) as output):
            self.assertEqual(publish_main(["--list-tables"]), 0)
        self.assertEqual(len(output.getvalue().splitlines()), 26)
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
            self.assertEqual(publish_main(["-sc", "E2025", "-tb", "games"]), 1)
        remote.assert_not_called()

    def test_dry_run_skips_quality_and_passes_read_only_mode(self):
        local = mock.MagicMock()
        local.cursor.return_value.__enter__.return_value.fetchone.return_value = (1,)
        remote = mock.MagicMock()
        with (mock.patch("neon_publish.main.connect", return_value=local),
              mock.patch("neon_publish.main.gold_main") as quality,
              mock.patch("neon_publish.main.neon_connect", return_value=remote),
              mock.patch("neon_publish.main.publish_season",
                         return_value={"games": (1, 1)}) as engine,
              mock.patch("sys.stdout", new_callable=io.StringIO)):
            self.assertEqual(publish_main(["-sc", "E2025", "-tb", "games",
                                           "--dry-run"]), 0)
        quality.assert_not_called()
        self.assertTrue(engine.call_args.kwargs["dry_run"])


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
