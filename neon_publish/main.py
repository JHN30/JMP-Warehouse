"""Publishing is paused until gold tables are rebuilt in feature 30."""

import argparse
import sys


PAUSED_MESSAGE = "Publishing paused (no gold tables until feature 30). Neon unchanged."


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="Report the paused state without connecting to Neon.")
    parser.add_argument("--list-tables", action="store_true",
                        help="List currently publishable tables (none until feature 30).")
    return parser


def main(argv=None):
    build_parser().parse_args(argv)
    print(PAUSED_MESSAGE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
