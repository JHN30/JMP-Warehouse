"""Competition and season-code helpers shared by every stage."""

import re
from datetime import date


COMPETITION_CODES = {"euroleague": "E", "eurocup": "U"}


def current_season_year(today=None):
    """Start year of the current season; a new season begins in September."""
    today = today or date.today()
    return today.year if today.month >= 9 else today.year - 1


def select_seasons(tokens, competition, available):
    """Resolve year, code, range, current, latest and all against available seasons.

    Returns (selected, missing). Raises ValueError for invalid tokens or when
    nothing requested is available.
    """
    prefix = COMPETITION_CODES[competition]
    available_set = set(available)
    if "all" in tokens or "latest" in tokens:
        if len(tokens) != 1:
            raise ValueError("'all' and 'latest' must each be used alone with -sc.")
        requested = available_set if tokens[0] == "all" else ({max(available_set)} if available_set else set())
    else:
        requested = set()
        for token in tokens:
            if token == "current":
                requested.add(f"{prefix}{current_season_year()}")
            elif re.fullmatch(rf"{prefix}\d{{4}}", token, re.IGNORECASE):
                requested.add(token.upper())
            elif re.fullmatch(r"\d{4}", token):
                requested.add(f"{prefix}{token}")
            elif match := re.fullmatch(r"(\d{4})-(\d{4})", token):
                first, last = map(int, match.groups())
                if first > last:
                    raise ValueError(f"Season range must ascend: {token}")
                requested.update(f"{prefix}{year}" for year in range(first, last + 1))
            else:
                raise ValueError(f"Invalid season code or range: {token}")
    missing = sorted(requested - available_set)
    selected = sorted(requested & available_set)
    if not selected:
        raise ValueError(
            f"No requested {competition} seasons are available. "
            f"Available: {', '.join(available) or '(none)'}"
        )
    return selected, missing
