"""Checks for the Neon publisher and the refresh command; no API, database or Neon is used."""

import io
import json
import os
import re
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

import pipeline
from neon_publish import publish
from neon_publish.main import build_parser, main as publish_main
from neon_publish.publish import (APP_TABLES, changed_games, drop_old_name_actions,
                                  drop_old_names, export_season, publish_season,
                                  remote_counts, shrink_problems)
from pipeline import season_code_for
from postgres_etl.flat_schema import TABLES


class PublishTests(unittest.TestCase):
    def test_app_tables_are_the_web_app_tables(self):
        self.assertEqual(len(APP_TABLES), 30)
        self.assertIn("app_standings", APP_TABLES)
        self.assertIn("standings_basicstandings", APP_TABLES)  # kept until the app switches
        self.assertTrue(set(APP_TABLES) <= set(TABLES))
        self.assertIn("play_by_play", APP_TABLES)
        self.assertIn("shots", APP_TABLES)
        self.assertNotIn("live_boxscores", APP_TABLES)
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
        self.assertIn("app_games: 380 -> 0 rows", problems[0])

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
                          "not a url at all s3cret-pass",
                          "postgresql://owner:s3cret@pass@example.neon.tech/db",   # raw @ in password
                          "postgresql://owner:s3cret@pass/x@example.neon.tech/db", # raw @, then /
                          "postgresql://owner:s3cret@pass?x@example.neon.tech/db", # raw @, then ?
                          "postgresql://owner:s3cret@pass#x@example.neon.tech/db"): # raw @, then #
            self.setUp()
            stages = FakeStages()
            code, result, next_step = self.run_refresh(stages, environ={pipeline.NEON_URL_ENV: malformed})
            self.assertEqual((code, result), (1, "STOPPED before Publish (Neon URL is malformed)"))
            self.assertEqual(stages.ran("publish"), [])
            self.assertTrue(pipeline.read_state(self.state)["publish_pending"])
            for text in (self.log_text(), self.console.getvalue(), next_step):
                for secret in ("s3cret-pass", "s3cret@pass", "pass@example"):
                    self.assertNotIn(secret, text)
        self.assertIn("%40", self.log_text())

    def test_percent_encoded_at_in_password_is_still_accepted(self):
        encoded = "postgresql://owner:s3cret%40pass@example.neon.tech/db"
        self.assertTrue(pipeline.looks_like_postgres_url(encoded))
        self.assertTrue(pipeline.looks_like_postgres_url(SECRET_URL))
        self.assertTrue(pipeline.looks_like_postgres_url(SECRET_URL + "?sslmode=require&channel_binding=require"))
        for raw_at in ("postgresql://owner:s3cret@pass@example.neon.tech/db",
                       "postgresql://owner:s3cret@pass/x@example.neon.tech/db",
                       "postgresql://owner:s3cret@pass?x@example.neon.tech/db",
                       "postgresql://owner:s3cret@pass#x@example.neon.tech/db"):
            self.assertFalse(pipeline.looks_like_postgres_url(raw_at), raw_at)

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


def sql_text(query):
    """Readable text of a psycopg2.sql object, without a real connection."""
    from psycopg2 import sql

    if isinstance(query, str):
        return query
    if isinstance(query, sql.Composed):
        return "".join(sql_text(part) for part in query.seq)
    if isinstance(query, sql.SQL):
        return query.string
    if isinstance(query, sql.Identifier):
        return ".".join(f'"{part}"' for part in query.strings)
    return repr(query.wrapped)  # sql.Literal


class FakeDatabase:
    """Just enough of a psycopg2 connection: relations with row counts, a statement log."""

    def __init__(self, tables=None, views=None, games=None, missing_columns=()):
        self.tables = dict(tables or {})   # name -> rows of the tested season
        self.views = dict(views or {})     # name -> base table
        # name -> {game_code: (rows, checksum)} for the per-game tables
        self.games = {name: dict(sums) for name, sums in (games or {}).items()}
        self.missing_columns = set(missing_columns)
        self.statements = []
        self.params = []
        self.result = None

    # connection
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def cursor(self):
        return self

    def rollback(self):
        pass

    def set_session(self, **_):
        pass

    # cursor
    def execute(self, query, params=None):
        text = sql_text(query)
        self.statements.append(text)
        self.params.append(params)
        names = re.findall(r'"(\w+)"', text)
        if "md5(string_agg" in text:
            table = re.search(r'FROM "(\w+)"', text).group(1)
            self.result = [(game, rows, digest)
                           for game, (rows, digest) in self.games.get(table, {}).items()]
        elif text.startswith("SELECT game_code, count(*) FROM"):
            self.result = [(game, rows) for game, (rows, _) in self.games.get(names[0], {}).items()]
        elif "FROM pg_class" in text:
            self.result = [(name, "r") for name in params[0] if name in self.tables]
            self.result += [(name, "v") for name in params[0] if name in self.views]
        elif text.startswith("SELECT count(*)"):
            relation = self.views.get(names[0], names[0])
            self.result = [(self.tables[relation],)]
        elif "information_schema.columns" in text:
            fields = TABLES[params[0].removeprefix("app_")].fields if params[0] in self.tables else ()
            self.result = [(field.name,) for field in fields
                           if field.name not in self.missing_columns]
        elif text.startswith("ALTER TABLE") and " RENAME TO " in text:
            self.tables[names[1]] = self.tables.pop(names[0])
        elif text.startswith("CREATE TABLE"):
            self.tables.setdefault(names[0], 0)
        elif text.startswith("ALTER TABLE") and " ADD COLUMN " in text:
            self.missing_columns.discard(names[1])
        elif text.startswith("CREATE VIEW"):
            self.views[names[0]] = names[1]
        elif text.startswith("DROP VIEW"):
            del self.views[names[0]]
        elif text.startswith("DELETE FROM") and "ANY(%s)" in text:
            for game in params[0]:
                rows, _ = self.games.get(names[0], {}).pop(game, (0, None))
                self.tables[names[0]] -= rows
        elif text.startswith("DELETE FROM"):
            self.tables[names[0]] = 0

    def copy_expert(self, query, spool):
        text = sql_text(query)
        self.statements.append(text)
        if "FROM STDIN" in text:
            table = re.findall(r'"(\w+)"', text)[0]
            self.tables[table] = self.tables.get(table, 0) + len(spool.read().splitlines())

    def fetchone(self):
        return self.result[0]

    def fetchall(self):
        return self.result

    def ddl(self):
        return [text for text in self.statements
                if text.split(" ", 1)[0] in ("ALTER", "CREATE", "DROP", "DELETE", "COPY")]


def publish_games(neon, dry_run=False):
    """Publish only `games` (380 local rows) with a faked local export."""
    local = FakeDatabase({"app_games": 380})
    lines = []
    spools = {"games": io.BytesIO(b"row\n" * 380)}
    with mock.patch.object(publish, "export_season", return_value=({"games": 380}, spools, {})):
        result = publish_season(local, neon, "euroleague", "E2025", ["games"],
                                dry_run=dry_run, log=lines.append)
    return result, lines


def changes_schema(neon):
    return [text for text in neon.ddl() if text.startswith(("ALTER", "CREATE"))]


class NeonRenameTests(unittest.TestCase):
    def test_counts_use_the_new_name_or_else_the_old_table(self):
        neon = FakeDatabase({"etl_flat_games": 380, "app_clubs": 20}, {"etl_flat_clubs": "app_clubs"})
        counts, planned, _ = remote_counts(neon, "E", "E2025", ["games", "clubs", "people"])
        self.assertEqual(counts, {"games": 380, "clubs": 20, "people": None})
        self.assertEqual(planned, [("rename", "etl_flat_games", "app_games"),
                                   ("view", "etl_flat_games", "app_games")])

    def test_dry_run_reports_the_rename_and_changes_nothing(self):
        neon = FakeDatabase({"etl_flat_games": 380})
        result, lines = publish_games(neon, dry_run=True)
        self.assertEqual(result, {"games": (380, 380)})
        self.assertEqual(lines, ["  etl_flat_games: would be renamed to app_games "
                                 "(old name kept as a view)"])
        self.assertEqual(neon.ddl(), [])
        self.assertEqual(neon.tables, {"etl_flat_games": 380})

    def test_publish_renames_and_keeps_a_view_before_replacing_rows(self):
        neon = FakeDatabase({"etl_flat_games": 375})
        result, lines = publish_games(neon)
        self.assertEqual(result, {"games": (375, 380)})
        columns = ", ".join(f'"{field.name}"' for field in TABLES["games"].fields)
        self.assertEqual(neon.ddl()[:4], [
            'ALTER TABLE "etl_flat_games" RENAME TO "app_games"',
            'CREATE VIEW "etl_flat_games" AS SELECT * FROM "app_games"',
            "DELETE FROM \"app_games\" WHERE competition_code = 'E' AND season_code = 'E2025'",
            f'COPY "app_games" ({columns}) FROM STDIN WITH (FORMAT CSV)',
        ])
        self.assertIn("  etl_flat_games: renamed to app_games (old name kept as a view)", lines)
        self.assertEqual((neon.tables, neon.views),
                         ({"app_games": 380}, {"etl_flat_games": "app_games"}))

        neon.statements.clear()  # a second publish renames nothing
        publish_games(neon)
        self.assertEqual(changes_schema(neon), [])

    def test_no_view_comes_back_after_the_old_names_were_dropped(self):
        neon = FakeDatabase({"app_games": 380})
        publish_games(neon)
        self.assertEqual(neon.views, {})
        self.assertEqual(changes_schema(neon), [])

    def test_old_and_new_tables_side_by_side_stop_before_any_change(self):
        neon = FakeDatabase({"etl_flat_games": 380, "app_games": 380})
        with self.assertRaisesRegex(ValueError, "Both etl_flat_games and app_games"):
            publish_games(neon)
        self.assertEqual(neon.ddl(), [])


class DropOldNamesTests(unittest.TestCase):
    def test_only_views_are_dropped_never_a_table(self):
        kinds = {"etl_flat_games": "view", "etl_flat_clubs": "table", "app_games": "table"}
        self.assertEqual(drop_old_name_actions(kinds),
                         [("keep", "etl_flat_clubs"), ("drop", "etl_flat_games")])
        self.assertEqual(drop_old_name_actions({}), [])

    def test_dry_run_lists_the_views_and_drops_nothing(self):
        neon = FakeDatabase({"app_games": 380, "etl_flat_clubs": 20}, {"etl_flat_games": "app_games"})
        lines = []
        drop_old_names(neon, dry_run=True, log=lines.append)
        self.assertEqual(neon.ddl(), [])
        self.assertIn("  etl_flat_games: view would be dropped", lines)
        self.assertIn("  etl_flat_clubs: still a table (not published since the rename); "
                      "left alone", lines)

    def test_drop_removes_the_views_and_reports_when_none_are_left(self):
        neon = FakeDatabase({"app_games": 380, "etl_flat_clubs": 20}, {"etl_flat_games": "app_games"})
        drop_old_names(neon, log=lambda _: None)
        self.assertEqual(neon.ddl(), ['DROP VIEW "etl_flat_games"'])
        self.assertEqual((set(neon.tables), neon.views), ({"app_games", "etl_flat_clubs"}, {}))
        lines = []
        drop_old_names(neon, log=lines.append)
        self.assertEqual(lines[-1], "No old-name views left in Neon.")

    def test_drop_old_names_cannot_be_combined_with_tables_or_seasons(self):
        for extra in (["-tb", "games"], ["-sc", "2025"]):
            with self.assertRaises(SystemExit), mock.patch("sys.stderr", io.StringIO()):
                publish_main(["--drop-old-names", *extra])
        self.assertIn("--drop-old-names", build_parser().format_help())


def publish_play_by_play(neon, local_sums, plan, local_rows):
    """Publish only `play_by_play` with a faked export of `plan` = (replace, remove)."""
    replace, remove = plan
    copied = sum(local_sums[game][0] for game in replace)
    spools = {"play_by_play": io.BytesIO(b"row\n" * copied)}
    lines = []
    exported = ({"play_by_play": local_rows}, spools,
                {"play_by_play": (replace, remove, len(local_sums))})
    with mock.patch.object(publish, "export_season", return_value=exported):
        result = publish_season(FakeDatabase(), neon, "euroleague", "E2025", ["play_by_play"],
                                log=lines.append)
    return result, lines


LOCAL_SUMS = {1: (10, "a"), 2: (12, "b"), 3: (8, "c")}


class PerGamePublishTests(unittest.TestCase):
    def test_changed_games_compares_rows_and_checksums(self):
        remote = {1: (10, "a"), 2: (12, "old"), 4: (5, "d")}
        self.assertEqual(changed_games(LOCAL_SUMS, remote), ([2, 3], [4]))
        self.assertEqual(changed_games(LOCAL_SUMS, dict(LOCAL_SUMS)), ([], []))
        self.assertEqual(changed_games(LOCAL_SUMS, {}), ([1, 2, 3], []))
        self.assertEqual(changed_games({1: (10, "a")}, {1: (9, "a")}), ([1], []))

    def test_first_publish_creates_the_table_and_copies_every_game(self):
        neon = FakeDatabase()
        result, lines = publish_play_by_play(neon, LOCAL_SUMS, ([1, 2, 3], []), 30)
        self.assertEqual(result, {"play_by_play": (None, 30)})
        self.assertTrue(neon.ddl()[0].startswith('CREATE TABLE IF NOT EXISTS "app_play_by_play"'))
        self.assertEqual(neon.tables["app_play_by_play"], 30)
        self.assertIn("  app_play_by_play: 3 of 3 game(s) replaced", lines)

    def test_unchanged_games_copy_nothing(self):
        neon = FakeDatabase({"app_play_by_play": 30}, games={"app_play_by_play": LOCAL_SUMS})
        result, lines = publish_play_by_play(neon, LOCAL_SUMS, ([], []), 30)
        self.assertEqual(result, {"play_by_play": (30, 30)})
        self.assertEqual(neon.ddl(), [])
        self.assertIn("  app_play_by_play: 0 of 3 game(s) replaced", lines)

    def test_only_changed_games_are_deleted_and_copied_and_extra_games_removed(self):
        remote = {1: (10, "a"), 2: (11, "old"), 3: (8, "c"), 4: (2, "d")}
        neon = FakeDatabase({"app_play_by_play": 31}, games={"app_play_by_play": remote})
        result, lines = publish_play_by_play(neon, LOCAL_SUMS, ([2], [4]), 30)
        self.assertEqual(result, {"play_by_play": (31, 30)})
        deletes = [(text, params) for text, params in zip(neon.statements, neon.params)
                   if text.startswith("DELETE")]
        self.assertEqual(len(deletes), 1)
        self.assertIn("AND game_code = ANY(%s)", deletes[0][0])
        self.assertEqual(deletes[0][1], ([2, 4],))
        self.assertEqual(sum(text.startswith("COPY") for text in neon.ddl()), 1)
        self.assertEqual(neon.tables["app_play_by_play"], 30)
        self.assertIn("  app_play_by_play: 1 of 3 game(s) replaced, 1 removed", lines)

    def test_dry_run_reports_games_and_changes_nothing(self):
        local = FakeDatabase({"app_play_by_play": 30}, games={"app_play_by_play": LOCAL_SUMS})
        neon = FakeDatabase({"app_play_by_play": 25},
                            games={"app_play_by_play": {1: (10, "a"), 2: (15, "x")}})
        lines = []
        result = publish_season(local, neon, "euroleague", "E2025", ["play_by_play"],
                                dry_run=True, log=lines.append)
        self.assertEqual(result, {"play_by_play": (25, 30)})
        self.assertEqual(lines, ["  app_play_by_play: 2 of 3 game(s) would be replaced"])
        self.assertEqual(neon.ddl(), [])

    def test_checksums_are_printed_in_utc_with_iso_dates(self):
        neon = FakeDatabase({"app_shots": 3}, games={"app_shots": {7: (3, "s")}})
        _, _, sums = remote_counts(neon, "E", "E2025", ["shots"])
        self.assertEqual(sums, {"shots": {7: (3, "s")}})
        checksum = neon.statements.index(next(text for text in neon.statements if "md5" in text))
        self.assertEqual(neon.statements[checksum - 2:checksum],
                         ["SET LOCAL TimeZone = 'UTC'", "SET LOCAL DateStyle = 'ISO'"])

    def test_missing_table_or_column_in_neon_means_every_game_is_new(self):
        _, _, sums = remote_counts(FakeDatabase(), "E", "E2025", ["play_by_play"])
        self.assertEqual(sums, {"play_by_play": {}})
        neon = FakeDatabase({"app_play_by_play": 30}, games={"app_play_by_play": LOCAL_SUMS},
                            missing_columns={"play_info"})
        _, _, sums = remote_counts(neon, "E", "E2025", ["play_by_play"])
        self.assertEqual(sums, {"play_by_play": {1: (10, None), 2: (12, None), 3: (8, None)}})
        self.assertFalse([text for text in neon.statements if "md5" in text])
        self.assertEqual(changed_games(LOCAL_SUMS, sums["play_by_play"]), ([1, 2, 3], []))

    def test_missing_column_still_removes_games_only_neon_has(self):
        remote = {**LOCAL_SUMS, 4: (2, "d")}
        neon = FakeDatabase({"app_play_by_play": 32}, games={"app_play_by_play": remote},
                            missing_columns={"play_info"})
        _, _, sums = remote_counts(neon, "E", "E2025", ["play_by_play"])
        plan = changed_games(LOCAL_SUMS, sums["play_by_play"])
        self.assertEqual(plan, ([1, 2, 3], [4]))
        neon.statements.clear()
        neon.params.clear()
        result, lines = publish_play_by_play(neon, LOCAL_SUMS, plan, 30)
        self.assertEqual(result, {"play_by_play": (32, 30)})
        self.assertIn('ALTER TABLE "app_play_by_play" ADD COLUMN "play_info" TEXT', neon.statements)
        delete = next(params for text, params in zip(neon.statements, neon.params)
                      if text.startswith("DELETE"))
        self.assertEqual(delete, ([1, 2, 3, 4],))
        self.assertEqual(neon.tables["app_play_by_play"], 30)
        self.assertIn("  app_play_by_play: 3 of 3 game(s) replaced, 1 removed", lines)

    def test_export_copies_only_the_changed_games(self):
        local = FakeDatabase({"app_play_by_play": 30, "app_games": 3},
                             games={"app_play_by_play": LOCAL_SUMS})
        counts, spools, plans = export_season(
            local, "E", "E2025", ["games", "play_by_play"],
            {"play_by_play": {1: (10, "a"), 2: (12, "old")}})
        self.assertEqual(counts, {"games": 3, "play_by_play": 30})
        self.assertEqual(plans, {"play_by_play": ([2, 3], [], 3)})
        copies = [text for text in local.statements if text.startswith("COPY")]
        self.assertNotIn("game_code = ANY", copies[0])
        self.assertIn("AND game_code = ANY([2, 3])", copies[1])
        for spool in spools.values():
            spool.close()

    def test_other_tables_still_replace_the_whole_season(self):
        neon = FakeDatabase({"app_games": 380})
        publish_games(neon)
        delete = next(text for text in neon.ddl() if text.startswith("DELETE"))
        self.assertNotIn("ANY", delete)


if __name__ == "__main__":
    unittest.main()
