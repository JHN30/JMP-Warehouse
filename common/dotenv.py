"""Read selected values from a local .env file without changing process state."""

from pathlib import Path


def read_env_value(path, name):
    """Return one .env value, or None when the file or name is absent."""
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if separator and key.strip().removeprefix("export ").strip() == name:
            return value.strip()
    return None
