"""Rename existing local Gold tables in place; never connect to Neon."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.db import DEFAULT_CONFIG, connect  # noqa: E402
from gold_etl.schema import GOLD_TABLES, PHYSICAL_TABLES, index_sql, physical_name  # noqa: E402


def rename_plan(existing):
    """Refuse collisions or missing tables before changing any relation."""
    plan = []
    for name in GOLD_TABLES:
        target = physical_name(name)
        if name != target and name in existing and target in existing:
            raise ValueError(f"Both gold.{name} and gold.{target} exist; resolve before migrating")
        if name not in existing and target not in existing:
            raise ValueError(f"Missing gold.{target} (and legacy gold.{name})")
        if name != target and name in existing:
            plan.append((name, target))
    unexpected = set(existing) - set(GOLD_TABLES) - set(PHYSICAL_TABLES)
    if unexpected:
        raise ValueError("Unexpected Gold tables: " + ", ".join(sorted(unexpected)))
    return plan


def migrate(connection, apply=False):
    from psycopg2 import sql

    with connection:
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL lock_timeout = '15s'")
            cursor.execute("SELECT c.relname FROM pg_class c JOIN pg_namespace n "
                           "ON n.oid=c.relnamespace WHERE n.nspname='gold' AND c.relkind IN ('r','p')")
            plan = rename_plan({row[0] for row in cursor.fetchall()})
            if apply:
                for source, target in plan:
                    cursor.execute(sql.SQL("ALTER TABLE {} RENAME TO {}").format(
                        sql.Identifier("gold", source), sql.Identifier(target)))
                for target in PHYSICAL_TABLES:
                    for statement in index_sql(target):
                        cursor.execute(statement)
    return plan


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Apply the local rename and app indexes atomically.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args(argv)
    connection = connect(args.config)
    try:
        plan = migrate(connection, args.apply)
        for source, target in plan:
            print(f"gold.{source} -> gold.{target}")
        print(f"{len(plan)} table(s) {'renamed; app indexes ensured' if args.apply else 'would be renamed (preview)'}")
        return 0
    finally:
        connection.close()


if __name__ == "__main__":
    sys.exit(main())
