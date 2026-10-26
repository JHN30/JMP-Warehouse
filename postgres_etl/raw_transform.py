"""Turn bronze endpoint responses into season-scoped relational rows.

Every row keeps its complete source object in ``payload``. The complete
responses stay in the bronze files.

Sources are the latest bronze version of each resource. They are addressed by
logical paths such as ``<season dir>/v2/games.json`` or
``<season dir>/live/12/play_by_play.json`` so parsers can keep using file names.
"""

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from flat_schema import COLUMN_NAMES, snake
from shared import BronzeStore, current_season_year


# Box-score measures that cannot be 0 for every player of a played game. When
# one is, the source did not record it for that game (plus/minus before E2012,
# fouls received in some early games). It becomes NULL instead of a fake 0, and
# the gap is listed in game_stat_gaps so it stays visible.
NEVER_ALL_ZERO = (
    "timePlayed", "points", "valuation", "fieldGoalsAttempted2", "fieldGoalsAttemptedTotal",
    "accuracyAttempted", "totalRebounds", "defensiveRebounds", "foulsCommited",
    "foulsReceived", "plusMinus",
)
NO_BOX_SCORE = "*"


def box_score_gaps(response):
    """Return NO_BOX_SCORE when a game has no player rows (e.g. a forfeit), else
    the set of NEVER_ALL_ZERO measures that are 0/missing for every player."""
    stats = [item.get("stats") or {}
             for side in ("local", "road")
             for item in (response.get(side) or {}).get("players") or []]
    if not stats:
        return NO_BOX_SCORE
    return {name for name in NEVER_ALL_ZERO
            if all(entry.get(name) in (0, None) for entry in stats)
            and any(entry.get(name) == 0 for entry in stats)}


def without_measures(values, gaps):
    """Copy a stats object with unrecorded measures set to None."""
    if not isinstance(values, dict):
        return values
    if gaps == NO_BOX_SCORE:
        return {key: (None if isinstance(value, (int, float)) and not isinstance(value, bool)
                      else value) for key, value in values.items()}
    return {key: (None if key in gaps else value) for key, value in values.items()}


COVID_RESTRICTIONS = ("2020-03-01", "2022-07-01")


def attendance(item):
    """Return (audience, audience_note). The source stores 0 both for games not
    played yet and for crowds that were not recorded (e.g. most of E2004/E2005),
    and cannot tell those apart from games behind closed doors. 0 therefore
    becomes NULL, and played games get a note the web app can show."""
    value = integer(item.get("audience"))
    if item.get("played") is not True or value is None:
        return None, None
    if value > 0:
        return value, None
    day = str(item.get("utcDate") or "")[:10]
    if COVID_RESTRICTIONS[0] <= day < COVID_RESTRICTIONS[1]:
        return None, "source reported 0: likely behind closed doors (COVID period)"
    return None, "source reported 0: attendance not recorded (or behind closed doors)"


def game_status(item, season_code, now=None):
    """Derive the app's game status: completed, scheduled, awaiting_result,
    postponed or cancelled, plus a note saying when it is inferred.

    The source marks some games Cancelled (E2021, Russian clubs) but leaves
    others "Confirmed" although they were never played (E2019, COVID). An
    unplayed game in a finished season is therefore reported as cancelled with
    an "inferred" note. awaiting_result depends on the load time.
    """
    if item.get("played") is True:
        return "completed", None
    source_status = str(item.get("gameStatus") or "").strip().lower()
    if source_status == "cancelled":
        return "cancelled", "cancelled by source"
    if "postpon" in source_status:
        return "postponed", "postponed by source"
    if int(season_code[1:]) < current_season_year():
        return "cancelled", "not played and the season is over (inferred)"
    scheduled = item.get("utcDate")
    now = now or datetime.now(timezone.utc)
    try:
        started = datetime.fromisoformat(str(scheduled).replace("Z", "+00:00"))
    except ValueError:
        return "scheduled", None
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    if started <= now:
        return "awaiting_result", "start time passed without a result (live, just finished or postponed)"
    return "scheduled", None


def nested(value, *keys):
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def code(value):
    if value is None:
        return None
    value = str(value).strip()
    return value or None


PBP_PERIODS = ("FirstQuarter", "SecondQuarter", "ThirdQuarter", "ForthQuarter", "ExtraTime")
STANDINGS_FILE = re.compile(r"(.+?)_(\d+)_(.+)\.json$")
LIVE_TEAM_MARKER = re.compile(r"(AC|CO)_[AB]")


def parse_source_timestamp(value):
    """Parse a source timestamp: a datetime, the 14-digit YYYYMMDDHHMMSS form
    (UTC), or ISO 8601 with an optional Z or offset. The loader's TIMESTAMP
    casts share it, so every date is read by one rule."""
    if isinstance(value, datetime):
        return value
    raw = str(value).strip()
    if re.fullmatch(r"\d{14}", raw):
        return datetime.strptime(raw, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def utc_wall_time(moment):
    """A zone-aware datetime as zone-less UTC; a zone-less one unchanged. Used for
    TIMESTAMP (without time zone) columns, so no session time zone can shift a
    value."""
    if moment.tzinfo is not None:
        return moment.astimezone(timezone.utc).replace(tzinfo=None)
    return moment


def normalized_name(value):
    """Upper-case letters only, accents removed: for matching names across feeds."""
    if not value:
        return None
    text = unicodedata.normalize("NFKD", str(value))
    letters = "".join(char for char in text if char.isalpha() and char.isascii())
    return letters.upper() or None


def integer(value):
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


class RawSeason:
    def __init__(self, data_root, competition, season_code):
        self.competition = competition
        self.season_code = season_code
        self.scope = {"competition_code": {"euroleague": "E", "eurocup": "U"}[competition],
                      "season_code": season_code}
        self.bronze_root = Path(data_root) / "bronze"
        self._used_versions = set()
        self.store = BronzeStore(self.bronze_root, competition, season_code,
                                 on_read=self._record_version)
        self.catalog_store = BronzeStore(self.bronze_root, competition, "_catalog",
                                         on_read=self._record_version)
        self.raw = self.store.directory
        self.catalog = self.catalog_store.directory / "v2" / "seasons.json"

    def _record_version(self, path):
        self._used_versions.add(path.relative_to(self.bronze_root).as_posix())

    def begin_table(self):
        """Start a fresh dependency set, including data held in lookup caches."""
        self._used_versions.clear()
        for name in ("_box_people_cache", "_season_person_codes_cache", "_pbp_people_cache"):
            self.__dict__.pop(name, None)

    def bronze_versions(self):
        return sorted(self._used_versions)

    # Logical path <-> bronze resource -------------------------------------
    def _locate(self, path):
        if path == self.catalog:
            return self.catalog_store, "v2/seasons"
        return self.store, path.relative_to(self.raw).with_suffix("").as_posix()

    def _paths(self, pattern):
        return [self.raw / f"{resource}.json" for resource in self.store.resources(pattern)]

    def read_bytes(self, path):
        store, resource = self._locate(path)
        return store.read_bytes(resource)

    def read(self, path):
        try:
            return json.loads(self.read_bytes(path).decode("utf-8"))
        except (OSError, ValueError, EOFError) as error:
            raise ValueError(f"Cannot read JSON from bronze {path}: {error}") from error

    # Live player id -> v2 person code ----------------------------------------
    def _game_box_people(self, game):
        """Players of one game's v2 box score, indexed three ways (cached per game)."""
        cache = self.__dict__.setdefault("_box_people_cache", {})
        if game not in cache:
            if len(cache) > 64:
                cache.clear()
            codes, by_number, by_name = set(), {}, {}
            response = self.store.read_json(f"v2/game_stats/{game}") or {}
            for side in ("local", "road"):
                for item in (response.get(side) or {}).get("players") or []:
                    person_code = code(nested(item, "player", "person", "code"))
                    club = code(nested(item, "player", "club", "code"))
                    if not person_code:
                        continue
                    codes.add(person_code)
                    number = code(nested(item, "player", "dorsal"))
                    if club and number:
                        by_number[(club, number)] = person_code
                    name = normalized_name(nested(item, "player", "person", "name"))
                    if club and name:
                        by_name[(club, name)] = person_code
            cache[game] = (codes, by_number, by_name)
        return cache[game]

    def _season_person_codes(self):
        if "_season_person_codes_cache" not in self.__dict__:
            self._season_person_codes_cache = {row["person_code"] for row in self.rows("people")
                                               if row["person_code"]}
        return self._season_person_codes_cache

    def _play_by_play_people(self, game):
        """Live id -> person code corrected by jersey number or name in one game's
        play-by-play; used for rows without a jersey number (shots, some events)."""
        cache = self.__dict__.setdefault("_pbp_people_cache", {})
        if game not in cache:
            if len(cache) > 64:
                cache.clear()
            mapping = {}
            if self.store.exists(f"live/{game}/play_by_play"):
                response = self.store.read_json(f"live/{game}/play_by_play") or {}
                for period in PBP_PERIODS:
                    for item in response.get(period) or []:
                        raw_id = code(item.get("PLAYER_ID"))
                        if raw_id and raw_id not in mapping:
                            person_code, method = self.resolve_live_person(
                                game, raw_id, item.get("CODETEAM"), item.get("DORSAL"),
                                item.get("PLAYER"), use_play_by_play=False)
                            if method in ("jersey_number", "name"):
                                mapping[raw_id] = person_code
            cache[game] = mapping
        return cache[game]

    def resolve_live_person(self, game, raw_id, club, number=None, name=None,
                            use_play_by_play=True):
        """Return (person_code, method) for a legacy live player id.

        Normally the id is "P" + the v2 code, but in some seasons the live API
        used other ids (e.g. Kanter E2008: P000936 vs v2 000110; Shakur E2007:
        "1"). The id is checked against the same game's v2 box score, then the
        player is matched there by team + jersey number or team + name.
        method is live_id, jersey_number, name, play_by_play or season_roster;
        (None, None) for team/coach markers and (None, "unmatched") otherwise.
        """
        raw_id = code(raw_id)
        if not raw_id or LIVE_TEAM_MARKER.fullmatch(raw_id):
            return None, None
        candidate = raw_id[1:] if raw_id.startswith("P") and len(raw_id) > 1 else raw_id
        codes, by_number, by_name = self._game_box_people(game)
        if candidate in codes:
            return candidate, "live_id"
        club = code(club)
        number = code(number)
        if club and number and (club, number) in by_number:
            return by_number[(club, number)], "jersey_number"
        key = normalized_name(name)
        if club and key and (club, key) in by_name:
            return by_name[(club, key)], "name"
        if use_play_by_play and raw_id in self._play_by_play_people(game):
            return self._play_by_play_people(game)[raw_id], "play_by_play"
        if candidate in self._season_person_codes():
            return candidate, "season_roster"
        return None, "unmatched"

    def _people_pages(self):
        """Latest page versions, ignoring stale pages beyond the current total."""
        pages = self._paths("v2/season_people_pages/*")
        if not pages:
            return []
        total = self.read(pages[0]).get("total")
        if not isinstance(total, int):
            return pages
        return [path for path in pages
                if int(path.stem.removeprefix("offset_")) < max(total, 1)]

    def files(self, table):
        single = {
            "seasons": ([self.catalog] if self.catalog_store.exists("v2/seasons") else []),
            "clubs": self._paths("v2/clubs"),
            "rounds": self._paths("v2/rounds"),
            "games": self._paths("v2/games"),
            "game_officials": self._paths("v2/games"),
            "game_period_scores": self._paths("v2/games"),
        }
        if table in single:
            return single[table]
        if table in ("people", "registrations"):
            # Club rosters (v2/rosters/*, no longer fetched) repeat the season people pages.
            return self._people_pages()
        patterns = {
            "game_player_stats": "v2/game_stats/*",
            "game_team_stats": "v2/game_stats/*",
            "game_stat_gaps": "v2/game_stats/*",
            "season_player_stats": "v3/season_stats/players_*",
            "season_team_stats": "v3/season_stats/teams_*",
            "standings": "v3/standings/*",
        }
        if table in patterns:
            return self._paths(patterns[table])
        live_names = {"play_by_play": "play_by_play", "shots": "shooting_charts"}
        if table in live_names:
            return self._paths(f"live/*/{live_names[table]}")
        raise KeyError(table)

    def rows(self, table, files=None):
        files = self.files(table) if files is None else files
        scope = self.scope
        read_json = self.read
        if table == "seasons":
            for path in files:
                for item in read_json(path).get("data", []):
                    if item.get("code") == self.season_code:
                        yield dict(scope, name=item.get("name"), start_year=integer(item.get("year")),
                                   champion_club_code=nested(item, "winner", "code"), payload=item)
            return

        if table in ("clubs", "rounds", "games", "game_officials", "game_period_scores"):
            for path in files:
                for item in read_json(path).get("data", []):
                    if table == "clubs":
                        club = code(item.get("code"))
                        if club:
                            yield dict(scope, club_code=club, name=item.get("name"), payload=item)
                    elif table == "rounds":
                        phase, number = code(item.get("phaseTypeCode")), integer(item.get("round"))
                        if phase and number is not None:
                            round_key = digest([phase, number, item.get("index"), item.get("name")])
                            yield dict(scope, round_key=round_key, phase_code=phase, round_number=number,
                                       name=item.get("name"), payload=item)
                    elif table == "games":
                        game = integer(item.get("gameCode"))
                        if game is None:
                            continue
                        local, road = item.get("local") or {}, item.get("road") or {}
                        local_code, road_code = nested(local, "club", "code"), nested(road, "club", "code")
                        played = item.get("played") is True
                        local_score = integer(local.get("score")) if played else None
                        road_score = integer(road.get("score")) if played else None
                        match_winner = None
                        if item.get("played") and local_score is not None and road_score is not None:
                            if local_score > road_score:
                                match_winner = local_code
                            elif road_score > local_score:
                                match_winner = road_code
                        status, status_note = game_status(item, self.season_code)
                        audience, audience_note = attendance(item)
                        yield dict(scope, game_code=game, status=status, status_note=status_note,
                                   audience=audience, audience_note=audience_note,
                                   phase_code=nested(item, "phaseType", "code"),
                                   round_number=integer(item.get("round")),
                                   scheduled_at=item.get("utcDate"), played=item.get("played"),
                                   local_club_code=local_code, road_club_code=road_code,
                                   local_score=local_score, road_score=road_score,
                                   local_standings_score=(integer(local.get("standingsScore")) if played else None),
                                   road_standings_score=(integer(road.get("standingsScore")) if played else None),
                                   match_winner_club_code=match_winner,
                                   champion_club_code=nested(item, "winner", "code"), payload=item)
                    elif table == "game_officials":
                        game = integer(item.get("gameCode"))
                        if game is None:
                            continue
                        for number in range(1, 5):
                            official = item.get(f"referee{number}")
                            if isinstance(official, dict):
                                yield dict(scope, game_code=game, official_number=number,
                                           official_code=code(official.get("code")),
                                           name=official.get("name"), payload=official)
                    else:
                        game = integer(item.get("gameCode"))
                        if game is None or item.get("played") is not True:
                            continue
                        for side in ("local", "road"):
                            partials = nested(item, side, "partials") or {}
                            for number in range(1, 5):
                                score = integer(partials.get(f"partials{number}"))
                                if score is not None:
                                    yield dict(scope, game_code=game, side=side,
                                               period_number=number, score=score, payload=partials)
                            for extra_number, value in (partials.get("extraPeriods") or {}).items():
                                number = integer(extra_number)
                                score = integer(value)
                                if number is not None and score is not None:
                                    yield dict(scope, game_code=game, side=side,
                                               period_number=4 + number, score=score, payload=partials)
            return

        if table in ("people", "registrations"):
            seen = set()
            for path in files:
                content = read_json(path)
                items = content.get("data", []) if isinstance(content, dict) else content
                if not isinstance(items, list):
                    continue
                for item in items:
                    person = item.get("person") or {}
                    person_key = code(person.get("code")) or code(item.get("externalId"))
                    if not person_key:
                        person_key = "anonymous-" + digest(person)[:16]
                    if table == "people":
                        if person_key in seen:
                            continue
                        seen.add(person_key)
                        yield dict(scope, person_key=person_key, person_code=code(person.get("code")),
                                   name=person.get("name"), payload=person)
                    else:
                        identity = [person_key, nested(item, "club", "code"), item.get("type"),
                                    item.get("startDate"), item.get("externalId")]
                        key = digest(identity)
                        if key in seen:
                            continue
                        seen.add(key)
                        yield dict(scope, registration_key=key, person_key=person_key,
                                   club_code=nested(item, "club", "code"), role_code=item.get("type"),
                                   active=item.get("active"), payload=item)
            return

        if table in ("game_player_stats", "game_team_stats", "game_stat_gaps"):
            for path in files:
                game = integer(path.stem)
                if game is None:
                    continue
                response = read_json(path)
                gaps = box_score_gaps(response)
                if table == "game_stat_gaps":
                    if gaps == NO_BOX_SCORE:
                        yield dict(scope, game_code=game, stat_name=NO_BOX_SCORE,
                                   reason="no player box score (e.g. forfeit); team stats are NULL",
                                   payload={})
                    for name in sorted(gaps if gaps != NO_BOX_SCORE else ()):
                        yield dict(scope, game_code=game,
                                   stat_name=COLUMN_NAMES.get(snake(name), snake(name)),
                                   reason="0 for every player: not recorded; stored as NULL",
                                   payload={})
                    continue
                for side in ("local", "road"):
                    side_data = response.get(side) or {}
                    if table == "game_team_stats":
                        if side_data:
                            compact = {"coach": side_data.get("coach"),
                                       "team": without_measures(side_data.get("team"), gaps),
                                       "total": without_measures(side_data.get("total"), gaps)}
                            yield dict(scope, game_code=game, side=side,
                                       coach_code=nested(side_data, "coach", "code"),
                                       points=nested(compact, "total", "points"), payload=compact)
                    else:
                        for ordinal, item in enumerate(side_data.get("players") or []):
                            person = nested(item, "player", "person") or {}
                            key = code(person.get("code")) or f"unknown-{ordinal}"
                            if gaps:
                                item = dict(item, stats=without_measures(item.get("stats"), gaps))
                            yield dict(scope, game_code=game, side=side, person_key=key,
                                       club_code=nested(item, "player", "club", "code"),
                                       points=nested(item, "stats", "points"), payload=item)
            return

        if table == "season_player_stats":
            # Phase codes come from the game list: RS, PI, PO, FF today, and TS
            # (Top 16) and others in older seasons.
            pattern = re.compile(
                r"players_(traditional|advanced|scoring|misc)_([A-Za-z0-9]+)_(perGame|accumulated)\.json$"
            )
            for path in files:
                match = pattern.fullmatch(path.name)
                if not match:
                    raise ValueError(f"Unexpected season stats filename: {path}")
                category, phase, mode = match.groups()
                for ordinal, item in enumerate(read_json(path).get("players") or []):
                    person_key = code(nested(item, "player", "code"))
                    team = nested(item, "player", "team") or {}
                    yield dict(scope, category=category, phase_code=phase, mode=mode,
                               entry_ordinal=ordinal,
                               person_key=person_key or f"unknown-{ordinal}",
                               club_code=team.get("code"), payload=item)
            return

        if table == "season_team_stats":
            pattern = re.compile(
                r"teams_((?:opponents_)?(?:traditional|advanced))_([A-Za-z0-9]+)_(perGame|accumulated)\.json$"
            )
            for path in files:
                match = pattern.fullmatch(path.name)
                if not match:
                    raise ValueError(f"Unexpected team stats filename: {path}")
                feed, phase, mode = match.groups()
                if feed.startswith("opponents_") or mode == "perGame":
                    continue  # archived only; no longer fetched and nothing reads them
                for item in read_json(path).get("teams") or []:
                    yield dict(scope, feed=feed, phase_code=phase, mode=mode,
                               club_code=code(nested(item, "team", "code")), payload=item)
            return

        if table == "standings":
            for path in files:
                match = STANDINGS_FILE.fullmatch(path.name)
                if not match:
                    raise ValueError(f"Unexpected standings filename: {path}")
                phase, round_number, feed = match.groups()
                for item in read_json(path).get("teams") or []:
                    club = nested(item, "club", "code")
                    if club:
                        yield dict(scope, phase_code=phase, round_number=int(round_number),
                                   feed=feed, club_code=club, position=integer(item.get("position")),
                                   payload=item)
            return

        if table in ("play_by_play", "shots"):
            for path in files:
                game = integer(path.parent.name)
                if game is None:
                    continue
                response = read_json(path)
                if table == "play_by_play":
                    for period in PBP_PERIODS:
                        for ordinal, item in enumerate(response.get(period) or []):
                            person_code, method = self.resolve_live_person(
                                game, item.get("PLAYER_ID"), item.get("CODETEAM"),
                                item.get("DORSAL"), item.get("PLAYER"))
                            yield dict(scope, game_code=game, period=period,
                                       event_ordinal=ordinal, play_number=integer(item.get("NUMBEROFPLAY")),
                                       club_code=code(item.get("CODETEAM")),
                                       player_code=code(item.get("PLAYER_ID")),
                                       person_code=person_code, person_code_method=method,
                                       play_type=item.get("PLAYTYPE"), payload=item)
                elif table == "shots":
                    for ordinal, item in enumerate(response.get("Rows") or []):
                        yield dict(scope, game_code=game, shot_ordinal=ordinal,
                                   play_number=integer(item.get("NUM_ANOT")),
                                   club_code=code(item.get("TEAM")),
                                   player_code=code(item.get("ID_PLAYER")),
                                   **dict(zip(("person_code", "person_code_method"),
                                              self.resolve_live_person(game, item.get("ID_PLAYER"),
                                                                       item.get("TEAM"), None,
                                                                       item.get("PLAYER")))),
                                   points=integer(item.get("POINTS")), coord_x=item.get("COORD_X"),
                                   coord_y=item.get("COORD_Y"), payload=item)
            return

        raise KeyError(table)
