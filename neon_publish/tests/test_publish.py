"""Publish engine and paused CLI checks."""

import io
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from neon_publish import publish
from neon_publish.main import main as publish_main
from neon_publish.publish import changed_games, export_season, publish_season, remote_counts, shrink_problems
from pipeline import StageFacts, build_parser, build_summary, refresh
from postgres_etl.flat_schema import TABLES


class PauseTests(unittest.TestCase):
    def test_cli_pauses_without_neon_url(self):
        with mock.patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(publish_main(["--dry-run"]), 0)
        self.assertIn("Publishing paused", output.getvalue())

    def test_pipeline_loads_without_prompting_for_neon_url(self):
        args = build_parser().parse_args(["--skip-fetch"])
        facts = StageFacts()
        stages = []
        class Log:
            def line(self, line):
                pass
        with tempfile.TemporaryDirectory() as root:
            def run_stage(command, cwd, env, emit):
                stages.append(command)
                emit("Quality E2025: 28 table(s), 100 rows, 0 error(s), 0 warning(s)")
                return 0
            result = refresh(args, "E2025", Log(), Path(root) / "state.json", facts,
                             stage_runner=run_stage, prompt=lambda _: self.fail("Neon URL prompt"),
                             environ={}, interactive=True)
        self.assertEqual(result[0], 0)
        self.assertEqual(len(stages), 1)
        self.assertIn("postgres_etl/main.py", stages[0][1])
        summary = build_summary("E2025", "OK", facts, 1, "log")
        self.assertIn("Publish:  paused (no gold tables until feature 30)", summary)


class EngineTests(unittest.TestCase):
    def test_shrink_guard(self):
        self.assertEqual(shrink_problems({"games": 80}, {"games": 100}),
                         ["games: 100 -> 80 rows"])
        self.assertEqual(shrink_problems({"games": 95}, {"games": 100}), [])


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
        elif text.startswith("SELECT to_regclass"):
            self.result = [(params[0] if params[0] in self.tables else None,)]
        elif text.startswith("SELECT count(*)"):
            relation = self.views.get(names[0], names[0])
            self.result = [(self.tables[relation],)]
        elif "information_schema.columns" in text:
            fields = TABLES[params[0]].fields if params[0] in self.tables else ()
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
        elif text.startswith("DROP TABLE"):
            del self.tables[names[0]]
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
    local = FakeDatabase({"games": 380})
    lines = []
    spools = {"games": io.BytesIO(b"row\n" * 380)}
    with mock.patch.object(publish, "export_season", return_value=({"games": 380}, spools, {})):
        result = publish_season(local, neon, "euroleague", "E2025", ["games"],
                                dry_run=dry_run, log=lines.append)
    return result, lines


def changes_schema(neon):
    return [text for text in neon.ddl() if text.startswith(("ALTER", "CREATE"))]


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
        self.assertTrue(neon.ddl()[0].startswith('CREATE TABLE IF NOT EXISTS "play_by_play"'))
        self.assertEqual(neon.tables["play_by_play"], 30)
        self.assertIn("  play_by_play: 3 of 3 game(s) replaced", lines)

    def test_unchanged_games_copy_nothing(self):
        neon = FakeDatabase({"play_by_play": 30}, games={"play_by_play": LOCAL_SUMS})
        result, lines = publish_play_by_play(neon, LOCAL_SUMS, ([], []), 30)
        self.assertEqual(result, {"play_by_play": (30, 30)})
        self.assertEqual(neon.ddl(), [])
        self.assertIn("  play_by_play: 0 of 3 game(s) replaced", lines)

    def test_only_changed_games_are_deleted_and_copied_and_extra_games_removed(self):
        remote = {1: (10, "a"), 2: (11, "old"), 3: (8, "c"), 4: (2, "d")}
        neon = FakeDatabase({"play_by_play": 31}, games={"play_by_play": remote})
        result, lines = publish_play_by_play(neon, LOCAL_SUMS, ([2], [4]), 30)
        self.assertEqual(result, {"play_by_play": (31, 30)})
        deletes = [(text, params) for text, params in zip(neon.statements, neon.params)
                   if text.startswith("DELETE")]
        self.assertEqual(len(deletes), 1)
        self.assertIn("AND game_code = ANY(%s)", deletes[0][0])
        self.assertEqual(deletes[0][1], ([2, 4],))
        self.assertEqual(sum(text.startswith("COPY") for text in neon.ddl()), 1)
        self.assertEqual(neon.tables["play_by_play"], 30)
        self.assertIn("  play_by_play: 1 of 3 game(s) replaced, 1 removed", lines)

    def test_dry_run_reports_games_and_changes_nothing(self):
        local = FakeDatabase({"play_by_play": 30}, games={"play_by_play": LOCAL_SUMS})
        neon = FakeDatabase({"play_by_play": 25},
                            games={"play_by_play": {1: (10, "a"), 2: (15, "x")}})
        lines = []
        result = publish_season(local, neon, "euroleague", "E2025", ["play_by_play"],
                                dry_run=True, log=lines.append)
        self.assertEqual(result, {"play_by_play": (25, 30)})
        self.assertEqual(lines, ["  play_by_play: 2 of 3 game(s) would be replaced"])
        self.assertEqual(neon.ddl(), [])

    def test_checksums_are_printed_in_utc_with_iso_dates(self):
        neon = FakeDatabase({"shots": 3}, games={"shots": {7: (3, "s")}})
        _, sums = remote_counts(neon, "E", "E2025", ["shots"])
        self.assertEqual(sums, {"shots": {7: (3, "s")}})
        checksum = neon.statements.index(next(text for text in neon.statements if "md5" in text))
        self.assertEqual(neon.statements[checksum - 2:checksum],
                         ["SET LOCAL TimeZone = 'UTC'", "SET LOCAL DateStyle = 'ISO'"])

    def test_missing_table_or_column_in_neon_means_every_game_is_new(self):
        _, sums = remote_counts(FakeDatabase(), "E", "E2025", ["play_by_play"])
        self.assertEqual(sums, {"play_by_play": {}})
        neon = FakeDatabase({"play_by_play": 30}, games={"play_by_play": LOCAL_SUMS},
                            missing_columns={"play_info"})
        _, sums = remote_counts(neon, "E", "E2025", ["play_by_play"])
        self.assertEqual(sums, {"play_by_play": {1: (10, None), 2: (12, None), 3: (8, None)}})
        self.assertFalse([text for text in neon.statements if "md5" in text])
        self.assertEqual(changed_games(LOCAL_SUMS, sums["play_by_play"]), ([1, 2, 3], []))

    def test_missing_column_still_removes_games_only_neon_has(self):
        remote = {**LOCAL_SUMS, 4: (2, "d")}
        neon = FakeDatabase({"play_by_play": 32}, games={"play_by_play": remote},
                            missing_columns={"play_info"})
        _, sums = remote_counts(neon, "E", "E2025", ["play_by_play"])
        plan = changed_games(LOCAL_SUMS, sums["play_by_play"])
        self.assertEqual(plan, ([1, 2, 3], [4]))
        neon.statements.clear()
        neon.params.clear()
        result, lines = publish_play_by_play(neon, LOCAL_SUMS, plan, 30)
        self.assertEqual(result, {"play_by_play": (32, 30)})
        self.assertIn('ALTER TABLE "play_by_play" ADD COLUMN "play_info" TEXT', neon.statements)
        delete = next(params for text, params in zip(neon.statements, neon.params)
                      if text.startswith("DELETE"))
        self.assertEqual(delete, ([1, 2, 3, 4],))
        self.assertEqual(neon.tables["play_by_play"], 30)
        self.assertIn("  play_by_play: 3 of 3 game(s) replaced, 1 removed", lines)

    def test_export_copies_only_the_changed_games(self):
        local = FakeDatabase({"play_by_play": 30, "games": 3},
                             games={"play_by_play": LOCAL_SUMS})
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
        neon = FakeDatabase({"games": 380})
        publish_games(neon)
        delete = next(text for text in neon.ddl() if text.startswith("DELETE"))
        self.assertNotIn("ANY", delete)


if __name__ == "__main__":
    unittest.main()
