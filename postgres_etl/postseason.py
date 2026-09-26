"""Postseason (Play-In + Playoffs + Final Four) player season stats.

The v3 statistics API cannot combine phases (``PhaseTypeCode=PO,FF`` returns
no rows), so the combined ``PS`` rows are derived from the v2 box scores in the
API's own row shape. Each rule was checked against the API's single-phase rows.
"""

from decimal import ROUND_HALF_EVEN, Decimal


POSTSEASON_PHASE = "PS"
POSTSEASON_PHASES = frozenset({"PI", "PO", "FF"})

# v3 traditional metric <- v2 box-score measure.
COUNTING = {
    "pointsScored": "points",
    "twoPointersMade": "fieldGoalsMade2",
    "twoPointersAttempted": "fieldGoalsAttempted2",
    "threePointersMade": "fieldGoalsMade3",
    "threePointersAttempted": "fieldGoalsAttempted3",
    "freeThrowsMade": "freeThrowsMade",
    "freeThrowsAttempted": "freeThrowsAttempted",
    "offensiveRebounds": "offensiveRebounds",
    "defensiveRebounds": "defensiveRebounds",
    "totalRebounds": "totalRebounds",
    "assists": "assistances",
    "steals": "steals",
    "turnovers": "turnovers",
    "blocks": "blocksFavour",
    "blocksAgainst": "blocksAgainst",
    "foulsCommited": "foulsCommited",
    "foulsDrawn": "foulsReceived",
    "pir": "valuation",
}
PERCENTAGES = {
    "twoPointersPercentage": ("twoPointersMade", "twoPointersAttempted"),
    "threePointersPercentage": ("threePointersMade", "threePointersAttempted"),
    "freeThrowsPercentage": ("freeThrowsMade", "freeThrowsAttempted"),
}
DOUBLE_MEASURES = ("points", "totalRebounds", "assistances", "steals", "blocksFavour")
# The statistic the fetcher asks the API to sort each feed by.
SORT_METRIC = {"traditional": "minutesPlayed", "misc": "gamesPlayed"}


def one_decimal(value):
    # The API rounds half to even (4.25 -> 4.2, 31.25 -> 31.2).
    return Decimal(value).quantize(Decimal("0.1"), rounding=ROUND_HALF_EVEN)


def postseason_games(games):
    """Played PI/PO/FF items of a v2 game list, oldest first."""
    return sorted((item for item in games
                   if item.get("played") is True
                   and (item.get("phaseType") or {}).get("code") in POSTSEASON_PHASES),
                  key=lambda item: (str(item.get("utcDate") or ""), item.get("gameCode")))


def club_game_counts(games):
    counts = {}
    for item in postseason_games(games):
        for side in ("local", "road"):
            club = ((item.get(side) or {}).get("club") or {}).get("code")
            if club:
                counts[club] = counts.get(club, 0) + 1
    return counts


def appearances(games, box_scores):
    """Yield one dict per player per played postseason game with time on court.

    ``games`` are v2 game-list items; ``box_scores`` maps game code to a v2
    box score whose unrecorded measures are already None.
    """
    for item in postseason_games(games):
        response = box_scores.get(item.get("gameCode")) or {}
        scores = {side: (item.get(side) or {}).get("score") for side in ("local", "road")}
        for side, other in (("local", "road"), ("road", "local")):
            won = None
            if scores[side] is not None and scores[other] is not None:
                won = scores[side] > scores[other]
            for player in (response.get(side) or {}).get("players") or []:
                person = (player.get("player") or {}).get("person") or {}
                person_key = str(person.get("code") or "").strip()
                stats = player.get("stats") or {}
                # Without a person code a player cannot be matched across games.
                if not person_key or (stats.get("timePlayed") or 0) <= 0:
                    continue
                club = (player.get("player") or {}).get("club") or {}
                yield {"person_key": person_key, "name": person.get("name"),
                       "club_code": club.get("code"), "club_name": club.get("name"),
                       "stats": stats, "won": won}


def _total(games, measure):
    values = [game["stats"].get(measure) for game in games]
    return None if any(value is None for value in values) else sum(values)


def _doubles(game):
    return sum(1 for measure in DOUBLE_MEASURES if (game["stats"].get(measure) or 0) >= 10)


def _player(games, identities, clubs):
    latest = games[-1]
    identity = identities.get(latest["person_key"]) or {}
    club = clubs.get(latest["club_code"]) or {}
    return {
        "code": latest["person_key"], "name": latest["name"],
        "age": identity.get("age"), "imageUrl": identity.get("imageUrl"),
        "team": {"code": latest["club_code"], "name": latest["club_name"],
                 "tvCodes": club.get("tvCodes"), "imageUrl": club.get("imageUrl")},
    }


def _player_rows(games, identities, clubs):
    """Return {(category, mode): payload} for one player's postseason games."""
    played = len(games)
    started = sum(1 for game in games if game["stats"].get("startFive") is True)
    minutes = sum(game["stats"]["timePlayed"] for game in games) / 60
    totals = {metric: _total(games, measure) for metric, measure in COUNTING.items()}
    percentages = {}
    for metric, (made, attempted) in PERCENTAGES.items():
        if totals[made] is None or not totals[attempted]:
            percentages[metric] = None
        else:
            percentages[metric] = one_decimal(Decimal(str(totals[made])) * 100
                                              / Decimal(str(totals[attempted])))
    player = _player(games, identities, clubs)
    base = {"player": player, "gamesPlayed": played, "gamesStarted": started}
    per_game = {metric: (None if value is None else one_decimal(Decimal(str(value)) / played))
                for metric, value in totals.items()}
    misc = dict(base,
                wins=sum(1 for game in games if game["won"] is True),
                losses=sum(1 for game in games if game["won"] is False),
                minutesPlayed=minutes / played,
                doubleDoubles=sum(1 for game in games if _doubles(game) >= 2),
                tripleDoubles=sum(1 for game in games if _doubles(game) >= 3))
    return {
        ("traditional", "accumulated"): dict(base, minutesPlayed=minutes, **totals, **percentages),
        ("traditional", "perGame"): dict(base, minutesPlayed=minutes / played,
                                         **per_game, **percentages),
        # The API's misc feed is the same in both modes, with per-game minutes.
        ("misc", "accumulated"): misc,
        ("misc", "perGame"): dict(misc),
    }


def postseason_payloads(games, box_scores, identities=None, clubs=None):
    """Return {(category, mode): [payload, ...]} sorted the way the API sorts.

    ``identities`` maps person code to a v3 ``player`` object and ``clubs``
    maps club code to a v3 ``team`` object, both from the season's API rows;
    they only fill display fields (age, images, TV codes).
    """
    by_player = {}
    for game in appearances(games, box_scores):
        by_player.setdefault(game["person_key"], []).append(game)
    club_games = club_game_counts(games)
    result = {}
    for player_games in by_player.values():
        # Like the API's per-game feeds, per-game rows need more than half of
        # the games; the bar is the player's own club so early exits qualify.
        qualified = len(player_games) * 2 > club_games.get(player_games[-1]["club_code"], 0)
        for key, payload in _player_rows(player_games, identities or {}, clubs or {}).items():
            if key[1] == "perGame" and not qualified:
                continue
            result.setdefault(key, []).append(payload)
    for (category, _), payloads in result.items():
        payloads.sort(key=lambda payload: (-payload[SORT_METRIC[category]],
                                           -payload["minutesPlayed"], payload["player"]["code"]))
    return result
