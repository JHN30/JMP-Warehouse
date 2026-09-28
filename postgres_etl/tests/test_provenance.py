"""Provenance loads use one transaction and one metadata identity per table."""

import sys
import tempfile
import types
import unittest
from datetime import timezone
from pathlib import Path
from unittest.mock import patch
from uuid import UUID


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flat_loader import FlatDatabaseLoader
from flat_schema import TABLES
from shared import BronzeStore


class FakeCursor:
    def __init__(self, operations):
        self.operations = operations

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, query, params=None):
        self.operations.append((query, params))


class FakeConnection:
    def __init__(self):
        self.operations = []
        self.commits = 0
        self.rollbacks = 0

    def __enter__(self):
        return self

    def __exit__(self, kind, *_):
        if kind is None:
            self.commits += 1
        else:
            self.rollbacks += 1
        return False

    def cursor(self):
        return FakeCursor(self.operations)

    def close(self):
        pass


class FakeSeason:
    scope = {"competition_code": "E", "season_code": "E2025"}
    season_code = "E2025"

    def __init__(self, count=1, fail_read=False):
        self.count = count
        self.fail_read = fail_read

    def rows(self, name, files):
        row = {field.name: None for field in TABLES[name].fields}
        row.update(self.scope, game_code=1)
        for _ in range(self.count):
            yield row
        if self.fail_read:
            raise ValueError("bad bronze row")

    def bronze_versions(self):
        return ["euroleague/E2025/v2/games/one_0123456789abcdef.json.gz"]


class ProvenanceWriterTests(unittest.TestCase):
    def run_load(self, season, connection=None, fail_insert=False):
        connection = connection or FakeConnection()
        package = types.ModuleType("psycopg2")
        package.__path__ = []
        extras = types.ModuleType("psycopg2.extras")
        extras.Json = lambda value: ("JSON", value)

        def execute_values(cursor, query, rows, page_size):
            cursor.operations.append((query, list(rows)))
            if fail_insert:
                raise RuntimeError("insert failed")

        extras.execute_values = execute_values
        package.extras = extras
        with patch.dict(sys.modules, {"psycopg2": package, "psycopg2.extras": extras}):
            result = FlatDatabaseLoader._load_table(
                connection, season, "games", ["v2/games.json"], 0
            )
        return connection, result

    def test_rows_and_log_share_one_identity_and_transaction(self):
        connection, count = self.run_load(FakeSeason())
        self.assertEqual((count, connection.commits, connection.rollbacks), (1, 1, 0))
        row_insert = next(value for query, value in connection.operations
                          if query.startswith('INSERT INTO "games"'))
        log_insert = next(value for query, value in connection.operations
                          if query.startswith('INSERT INTO "load_log"'))
        row_id, row_time = row_insert[0][-2:]
        self.assertEqual(UUID(row_id).version, 4)
        self.assertEqual(row_time.tzinfo, timezone.utc)
        self.assertEqual(log_insert[:3], ("E", "E2025", "games"))
        self.assertEqual(log_insert[3:6], (row_id, row_time, 1))
        self.assertEqual(log_insert[6], ("JSON", FakeSeason().bronze_versions()))
        self.assertLess(next(i for i, (query, _) in enumerate(connection.operations)
                             if query.startswith('DELETE FROM "games"')),
                        next(i for i, (query, _) in enumerate(connection.operations)
                             if query.startswith('INSERT INTO "load_log"')))

    def test_zero_rows_log_and_rerun_keeps_previous_history(self):
        connection = FakeConnection()
        self.run_load(FakeSeason(count=0), connection)
        self.run_load(FakeSeason(count=0), connection)
        logs = [params for query, params in connection.operations
                if query.startswith('INSERT INTO "load_log"')]
        self.assertEqual([params[5] for params in logs], [0, 0])
        self.assertNotEqual(logs[0][3], logs[1][3])
        self.assertEqual(connection.commits, 2)
        self.assertFalse(any(query.startswith('DELETE FROM "load_log"')
                             for query, _ in connection.operations))

    def test_rerun_points_current_rows_to_the_new_log(self):
        connection = FakeConnection()
        self.run_load(FakeSeason(), connection)
        self.run_load(FakeSeason(), connection)
        rows = [values[0] for query, values in connection.operations
                if query.startswith('INSERT INTO "games"')]
        logs = [params for query, params in connection.operations
                if query.startswith('INSERT INTO "load_log"')]
        self.assertNotEqual(logs[0][3], logs[1][3])
        self.assertEqual(rows[1][-2:], logs[1][3:5])

    def test_failed_read_or_insert_rolls_back_without_log(self):
        for season, fail_insert in ((FakeSeason(fail_read=True), False),
                                    (FakeSeason(), True)):
            with self.subTest(fail_insert=fail_insert):
                connection = FakeConnection()
                with self.assertRaises((ValueError, RuntimeError)):
                    self.run_load(season, connection, fail_insert)
                self.assertEqual((connection.commits, connection.rollbacks), (0, 1))
                self.assertFalse(any(query.startswith('INSERT INTO "load_log"')
                                     for query, _ in connection.operations))

    def test_dry_run_never_connects_or_writes_log(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            BronzeStore(root / "bronze", "euroleague", "E2025").write(
                "v2/games", b'{"data":[]}'
            )
            loader = FlatDatabaseLoader(root, "euroleague", ["E2025"], ["games"],
                                        root / "unused.json", dry_run=True)
            with patch("flat_loader.connect", side_effect=AssertionError("connected")):
                self.assertEqual(loader.run(), 0)

    def test_no_source_skips_replacement_and_log(self):
        class NoSourceSeason:
            def begin_table(self):
                pass

            def files(self, name):
                return []

        connection = FakeConnection()
        loader = FlatDatabaseLoader("unused", "euroleague", ["E2025"], ["games"],
                                    "unused.json")
        with patch("flat_loader.connect", return_value=connection), \
                patch("flat_loader.FlatSeason", return_value=NoSourceSeason()):
            self.assertEqual(loader.run(), 0)
        self.assertTrue(any(query.startswith('CREATE TABLE IF NOT EXISTS "load_log"')
                            for query, _ in connection.operations))
        self.assertFalse(any(query.startswith(('DELETE', 'INSERT'))
                             for query, _ in connection.operations))


if __name__ == "__main__":
    unittest.main()
