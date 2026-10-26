"""On-court event counts per player line (feature 32), for the per-game player rates.

For every box-score player of a side whose game has play-by-play and starters, count the
team's and the opponent's events while the player was on court, and his own events in those
stretches. Events are attributed by event order to the lineup on court, as feature 29b's
stints are; opponent possessions come from feature 19a's counted possessions. Free-throw
trips (`ft_trips`) are the chances, besides made field goals, that EuroLeague credits
assists on. `derive_counts`
is pure; `advanced.read_rows` reads the inputs. Nothing reads Gold or Neon.
"""

from decimal import Decimal

from lineups import _walk
from possessions import (FREE_THROWS, MADE, MISSED, PLAYS, _count, _game_end, _sort_key,
                         events_by_game)

THREES = {"3FGM", "3FGA", "3FGAB"}
# Count names per play type; `two_pa` is added for field-goal attempts that are not threes.
KINDS = {**{kind: ("fga", "fgm") for kind in MADE}, **{kind: ("fga",) for kind in MISSED},
         **{kind: ("fta",) for kind in FREE_THROWS},
         "TO": ("tov",), "O": ("oreb",), "D": ("dreb",),
         "AS": ("ast",), "ST": ("stl",), "FV": ("blk",)}
NAMES = ("fga", "fgm", "two_pa", "fta", "ft_trips", "tov", "oreb", "dreb", "ast", "stl", "blk")


def _blank():
    return {"own": dict.fromkeys(NAMES, Decimal(0)), "team": dict.fromkeys(NAMES, Decimal(0)),
            "opp": dict.fromkeys(NAMES, Decimal(0)), "opp_possessions": Decimal(0)}


def _names(kind):
    names = KINDS.get(kind, ())
    if "fga" in names and kind not in THREES:
        names += ("two_pa",)
    return names


def _moment(event):
    return event.get("club_code"), event["period"], event.get("marker_time")


def _trip_starts(ordered):
    """`id`s of the free throws that start a trip: a run of one club's free throws at one
    period and clock, with no other play between them. A run right after the club's made
    field goal at the same clock is an and-one, not a trip."""
    starts, previous = set(), None
    for event in ordered:
        kind = event["play_type"]
        if kind not in PLAYS:
            continue
        if kind in FREE_THROWS:
            same = previous is not None and _moment(previous) == _moment(event)
            if not (same and previous["play_type"] in FREE_THROWS | MADE):
                starts.add(id(event))
        previous = event
    return starts


def derive_counts(games, players, events):
    """{(game_code, side, person_key): counts} for box-score players of qualifying sides.

    `counts` holds `own`, `team` and `opp` dicts of the `NAMES` counts plus
    `opp_possessions`. A side qualifies when its game is played, has events, both clubs are
    known and the side has starters; its players never seen on court get zero counts.
    """
    by_game, roster, starters = events_by_game(events), {}, {}
    for player in players:
        key = (player["game_code"], player["side"])
        roster.setdefault(key, []).append(player["person_key"])
        if player.get("started"):
            starters.setdefault(key, []).append(player["person_key"])
    result = {}
    for game in games:
        code = game["game_code"]
        clubs = {"local": game.get("local_club_code"), "road": game.get("road_club_code")}
        if game.get("played") is not True or code not in by_game or not all(clubs.values()):
            continue
        sides = [side for side in clubs if starters.get((code, side))]
        if not sides:
            continue
        ordered = sorted(by_game[code], key=_sort_key)
        lineup_starters = {side: starters.get((code, side), []) for side in clubs}
        _, stint_of = _walk(ordered, clubs, lineup_starters, _game_end(ordered))
        trips = _trip_starts(ordered)
        counts = {side: {person: _blank() for person in roster[(code, side)]} for side in sides}
        index = {clubs["local"]: 0, clubs["road"]: 1}
        names = ("local", "road")
        for event in ordered:
            stint = stint_of.get(id(event))
            own_index = index.get(event.get("club_code"))
            kinds = _names(event["play_type"])
            if id(event) in trips:
                kinds += ("ft_trips",)
            if stint is None or own_index is None or not kinds:
                continue
            for side_index, role in ((own_index, "team"), (1 - own_index, "opp")):
                side = names[side_index]
                if side not in counts:
                    continue
                for person in stint["lineup"][side_index]:
                    entry = counts[side].setdefault(person, _blank())
                    for name in kinds:
                        entry[role][name] += 1
                    if role == "team" and person == event.get("person_code"):
                        for name in kinds:
                            entry["own"][name] += 1
        ends = []
        _count(ordered, set(clubs.values()), ends)
        for club, closing in ends:
            stint = stint_of.get(id(closing))
            opponent = 1 - index[club]
            if stint is None or names[opponent] not in counts:
                continue
            for person in stint["lineup"][opponent]:
                counts[names[opponent]].setdefault(person, _blank())["opp_possessions"] += 1
        for side, people in counts.items():
            for person in roster[(code, side)]:
                result[(code, side, person)] = people[person]
    return result
