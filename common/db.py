"""PostgreSQL connection and console helpers shared by every stage."""

import json
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = PROJECT_ROOT / "postgres_etl" / "config_connection.json"
LOG_ROOT = PROJECT_ROOT / "logs"


def connect(config_path=DEFAULT_CONFIG):
    """Connect to local PostgreSQL with the settings in a JSON file."""
    try:
        import psycopg2
    except ImportError as error:
        raise RuntimeError(
            "PostgreSQL access requires psycopg2 (python -m pip install psycopg2-binary)."
        ) from error
    with Path(config_path).open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    return psycopg2.connect(**config)


def elapsed(started):
    seconds = int(time.monotonic() - started)
    return f"{seconds // 3600:02d}:{seconds // 60 % 60:02d}:{seconds % 60:02d}"


class Tee:
    """Write console output to the terminal and a run log."""

    def __init__(self, *streams):
        self.streams = streams

    def write(self, value):
        for stream in self.streams:
            stream.write(value)

    def flush(self):
        for stream in self.streams:
            stream.flush()


def log_directory(tool):
    """Return logs/<tool>/, created on demand."""
    directory = LOG_ROOT / tool
    directory.mkdir(parents=True, exist_ok=True)
    return directory
