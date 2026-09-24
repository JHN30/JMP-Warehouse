"""Make the project-wide ``common`` package importable from this folder's scripts."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common.bronze import BronzeStore, available_scopes  # noqa: E402,F401
from common.db import DEFAULT_CONFIG, connect, elapsed  # noqa: E402,F401
from common.seasons import COMPETITION_CODES, current_season_year  # noqa: E402,F401
