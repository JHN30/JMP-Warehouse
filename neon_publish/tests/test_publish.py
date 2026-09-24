"""Checks for the Neon publisher and the refresh command; no API, database or Neon is used."""

import io
import json
import os
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

import pipeline
from neon_publish.main import build_parser
from neon_publish.publish import APP_TABLES, shrink_problems
from pipeline import season_code_for
from postgres_etl.flat_schema import TABLES


class PublishTests(unittest.TestCase):
    def test_app_tables_are_the_web_app_tables(self):
        self.assertEqual(len(APP_TABLES), 22)
        self.assertIn("app_standings", APP_TABLES)
        self.assertIn("standings_basicstandings", APP_TABLES)  # kept until the app switches
        self.assertTrue(set(APP_TABLES) <= set(TABLES))
        self.assertNotIn("play_by_play", APP_TABLES)
        self.assertNotIn("source_payloads", APP_TABLES)

    def test_growth_and_small_changes_are_allowed(self):
        self.assertEqual(shrink_problems({"games": 380, "people": 95},
                                         {"games": 380, "people": 100}), [])
        self.assertEqual(shrink_problems({"games": 380}, {"games": None}), [])
        self.assertEqual(shrink_problems({"standings_basicstandings": 20},
                                         {"standings_basicstandings": 0}), [])

    def test_emptying_or_large_shrink_is_refused(self):
        problems = shrink_problems({"games": 0, "people": 80},
                                   {"games": 380, "people": 100})
        self.assertEqual(len(problems), 2)
        self.assertIn("etl_flat_games: 380 -> 0 rows", problems[0])

    def test_cli_defaults_to_current_season_and_all_app_tables(self):
        args = build_parser().parse_args([])
        self.assertEqual(args.season_code, ["current"])
        self.assertEqual(args.table, ["all"])
        self.assertFalse(args.allow_shrink)


class PipelineTests(unittest.TestCase):
    def test_season_code_tokens(self):
        self.assertEqual(season_code_for("euroleague", "2026"), "E2026")
        self.assertEqual(season_code_for("euroleague", "e2025"), "E2025")
        self.assertEqual(season_code_for("eurocup", "2024"), "U2024")
        with mock.patch("pipeline.current_season_year", return_value=2026):
            self.assertEqual(season_code_for("euroleague", "current"), "E2026")
        with self.assertRaises(ValueError):
            season_code_for("euroleague", "U2025")

    def test_current_season_rollover_is_september(self):
        from tables_to_csv.utils import current_season_year
        self.assertEqual(current_season_year(date(2026, 9, 24)), 2026)


LOAD_OK = ["Season E2026 | elapsed 00:00:00", "Finished: 2,430 rows across 1 season(s) in 00:00:00",
           "Read-only quality checks",
           "Quality E2026: 9 table(s), 2,430 rows, 0 error(s), 1 warning(s) | elapsed 00:00:00",
           "  WARN etl_flat_game_period_scores: empty_table (0 row(s))"]
PUBLISH_OK = ["Season E2026 | elapsed 00:00:00", "  etl_flat_games: 380 -> 380 rows",
              "  app_standings: missing -> 0 rows", "Season E2026 committed in 00:00:05"]
PUBLISH_DRY = ["  etl_flat_games: 380 would become 381 rows", "Season E2026 checked in 00:00:01"]
SECRET_URL = "postgresql://owner:s3cret-pass@example.neon.tech/db"


class FakeStages:
    """Stand-in for run_stage: returns recorded output per stage, records calls."""

    def __init__(self, changed=1, load=(0, LOAD_OK), publish=(0, PUBLISH_OK)):
        self.changed, self.load, self.publish = changed, load, publish
        self.calls = []

    def __call__(self, command, cwd, env, emit):
        name = ("publish" if "neon_publish/main.py" in command else
                "load" if "postgres_etl/main.py" in command else "fetch")
        self.calls.append((name, env))
        if name == "fetch":
            path = Path(command[command.index("--summary-file") + 1])
            path.write_text(json.dumps({"changed_resources": ["E2026/v2/games"] * self.changed,
                                        "failed_requests": 0}), encoding="utf-8")
            emit("Changed resources: 1  ---  Failed requests: 0")
            return 0
        code, lines = self.load if name == "load" else self.publish
        for line in lines:
            emit(line)
        return code

    def ran(self, name):
        return [env for stage, env in self.calls if stage == name]


class RefreshCommandTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.console = io.StringIO()
        self.log = pipeline.RunLog(self.root / "refresh.log", console=self.console)
        self.addCleanup(self.log.close)
        self.state = self.root / "state.json"
        self.facts = pipeline.StageFacts()

    def run_refresh(self, stages, argv=(), environ=None, prompt=None, interactive=True):
        args = pipeline.build_parser().parse_args(list(argv))
        prompt = prompt or mock.Mock(side_effect=AssertionError("prompt not expected"))
        return pipeline.refresh(args, "E2026", self.log, self.state, self.facts,
                                stage_runner=stages, prompt=prompt,
                                environ={pipeline.NEON_URL_ENV: SECRET_URL} if environ is None else environ,
                                interactive=interactive)

    def log_text(self):
        self.log.file.flush()
        return (self.root / "refresh.log").read_text(encoding="utf-8")

    def test_stage_output_reaches_console_and_log(self):
        code, result, _ = self.run_refresh(FakeStages())
        self.assertEqual((code, result), (0, "OK"))
        for text in ("Changed resources: 1", "Quality E2026: 9 table(s)", "etl_flat_games: 380 -> 380 rows"):
            self.assertIn(text, self.console.getvalue())
            self.assertIn(text, self.log_text())
        self.assertFalse(pipeline.read_state(self.state)["publish_pending"])

    def test_failing_stage_stops_with_its_exit_code_and_keeps_the_publish_pending(self):
        stages = FakeStages(load=(1, ["ETL failed: standings: Invalid number: 'x'"]))
        code, result, next_step = self.run_refresh(stages)
        self.assertEqual((code, result), (1, "FAILED at Load (exit 1)"))
        self.assertEqual(stages.ran("publish"), [])
        self.assertTrue(pipeline.read_state(self.state)["publish_pending"])
        self.assertIn("stays pending", next_step)

    def test_nothing_changed_stops_after_the_fetch(self):
        stages = FakeStages(changed=0)
        self.assertEqual(self.run_refresh(stages)[:2], (0, "NOTHING TO DO"))
        self.assertEqual([name for name, _ in stages.calls], ["fetch"])

    def test_real_stage_runner_streams_utf8_and_returns_the_exit_code(self):
        lines = []
        code = pipeline.run_stage(
            [sys.executable, "-c", "print('Jasikevi\\u010dius \\u0160ar\\u016bnas'); raise SystemExit(3)"],
            self.root, dict(os.environ, **pipeline.CHILD_ENV), lines.append)
        self.assertEqual((code, lines), (3, ["Jasikevičius Šarūnas"]))

    def test_summary_for_a_successful_run(self):
        self.facts.changed, self.facts.failed_requests = 3, 0
        self.facts.load_lines[:], self.facts.publish_lines[:] = LOAD_OK, PUBLISH_OK
        text = "\n".join(pipeline.build_summary("E2026", "OK", self.facts, 75, "logs/refresh/x.log"))
        for expected in ("Result:   OK", "Time: 1 min 15 s", "Fetch:    3 changed resource(s), 0 failed request(s)",
                         "Load:     2,430 rows loaded; quality 0 error(s), 1 warning(s)",
                         "WARN etl_flat_game_period_scores: empty_table", "Publish:  committed",
                         "etl_flat_games: 380 -> 380", "app_standings: missing -> 0", "Log:      logs/refresh/x.log"):
            self.assertIn(expected, text)

    def test_summary_shows_not_run_never_zero(self):
        text = "\n".join(pipeline.build_summary("E2026", "NOTHING TO DO", pipeline.StageFacts(), 3, "x.log"))
        for stage in ("Fetch:    not run", "Load:     not run", "Publish:  not run"):
            self.assertIn(stage, text)

    def test_summary_for_dry_run_and_failures(self):
        self.facts.load_lines[:] = LOAD_OK
        self.facts.publish_lines[:] = PUBLISH_DRY
        dry = "\n".join(pipeline.build_summary("E2026", "OK (dry run)", self.facts, 5, "x.log"))
        self.assertIn("Publish:  dry run (Neon unchanged)", dry)
        self.assertIn("etl_flat_games: 380 -> 381", dry)
        self.facts.publish_lines[:] = ["Publish failed (Neon unchanged for the failing season): shrink"]
        failed = "\n".join(pipeline.build_summary("E2026", "FAILED at Publish (exit 1)", self.facts, 5,
                                                  "x.log", "Neon keeps its previous rows."))
        self.assertIn("Publish:  not completed", failed)
        self.assertIn("Publish failed (Neon unchanged", failed)
        self.assertIn("Next:     Neon keeps its previous rows.", failed)
        self.facts.load_lines[:] = ["ETL failed: games.audience from @audience (E2026): Invalid integer"]
        self.assertIn("ETL failed: games.audience",
                      "\n".join(pipeline.build_summary("E2026", "FAILED at Load (exit 1)", self.facts, 1, "x")))

    def test_neon_url_from_environment_is_used_without_asking(self):
        stages = FakeStages()
        self.run_refresh(stages)
        self.assertEqual(stages.ran("publish")[0][pipeline.NEON_URL_ENV], SECRET_URL)
        self.assertNotIn(SECRET_URL, self.log_text())
        self.assertIn(f"Neon URL: from {pipeline.NEON_URL_ENV}.", self.log_text())

    def test_neon_url_is_asked_only_when_publishing(self):
        prompt = mock.Mock(return_value=f"  {SECRET_URL}  ")
        stages = FakeStages()
        self.assertEqual(self.run_refresh(stages, environ={}, prompt=prompt)[:2], (0, "OK"))
        prompt.assert_called_once()
        self.assertEqual(stages.ran("publish")[0][pipeline.NEON_URL_ENV], SECRET_URL)
        self.assertNotIn(SECRET_URL, self.log_text())
        self.assertNotIn(pipeline.NEON_URL_ENV, stages.ran("load")[0])  # only the publish stage gets it
        nothing = FakeStages(changed=0)
        self.run_refresh(nothing, environ={}, prompt=prompt)
        prompt.assert_called_once()  # nothing to publish, so no second question

    def test_quoted_neon_url_is_unquoted(self):
        for quoted in (f'"{SECRET_URL}"', f"'{SECRET_URL}'", f'  "{SECRET_URL}" '):
            self.assertEqual(pipeline.resolve_neon_url({pipeline.NEON_URL_ENV: quoted}, None, True)[0],
                             SECRET_URL)
            self.assertEqual(pipeline.resolve_neon_url({}, lambda _: quoted, True)[0], SECRET_URL)

    def test_publish_output_echoing_the_url_or_password_is_redacted(self):
        leak = [f'Publish failed (Neon unchanged for the failing season): invalid dsn: '
                f'invalid connection option "{SECRET_URL}"',
                "  password fragment: s3cret-pass"]
        stages = FakeStages(publish=(1, leak))
        code, result, _ = self.run_refresh(stages)
        self.assertEqual((code, result), (1, "FAILED at Publish (exit 1)"))
        summary = "\n".join(pipeline.build_summary("E2026", result, self.facts, 1, "x.log"))
        for text in (self.log_text(), self.console.getvalue(), summary):
            self.assertNotIn(SECRET_URL, text)
            self.assertNotIn("s3cret-pass", text)
        self.assertIn('invalid connection option "***"', summary)

    def test_malformed_neon_url_is_refused_before_publish_and_never_shown(self):
        for malformed in (f'"{SECRET_URL}?sslmode=require',          # one stray quote
                          f"“{SECRET_URL}”",                 # curly quotes
                          "not a url at all s3cret-pass"):
            self.setUp()
            stages = FakeStages()
            code, result, next_step = self.run_refresh(stages, environ={pipeline.NEON_URL_ENV: malformed})
            self.assertEqual((code, result), (1, "STOPPED before Publish (Neon URL is malformed)"))
            self.assertEqual(stages.ran("publish"), [])
            self.assertTrue(pipeline.read_state(self.state)["publish_pending"])
            for text in (self.log_text(), self.console.getvalue(), next_step):
                self.assertNotIn("s3cret-pass", text)

    def test_redactor_hides_credentials_even_when_the_url_does_not_parse(self):
        raw = f"“{SECRET_URL}”"
        redact = pipeline.redactor(raw)
        echoed = 'invalid connection option "“postgresql://owner:s3cret-pass@example.neon.tech/db"'
        self.assertNotIn("s3cret-pass", redact(echoed))
        self.assertNotIn("owner:s3cret-pass", redact("owner:s3cret-pass"))

    def test_unfinished_load_reports_unknown_rows_not_zero(self):
        self.facts.load_lines[:] = ["ETL failed: games.audience from @audience (E2026): Invalid integer"]
        text = "\n".join(pipeline.build_summary("E2026", "FAILED at Load (exit 1)", self.facts, 1, "x"))
        self.assertIn("rows loaded unknown (the load did not finish)", text)
        self.assertNotIn("no rows", text)

    def test_empty_answer_or_no_console_stops_before_publish(self):
        for kwargs in ({"prompt": mock.Mock(return_value="   ")}, {"interactive": False}):
            stages = FakeStages()
            code, result, next_step = self.run_refresh(stages, environ={}, **kwargs)
            self.assertEqual((code, result), (1, "STOPPED before Publish (no Neon URL)"))
            self.assertEqual(stages.ran("publish"), [])
            self.assertTrue(pipeline.read_state(self.state)["publish_pending"])
            self.assertIn(pipeline.NEON_URL_ENV, next_step)


if __name__ == "__main__":
    unittest.main()
