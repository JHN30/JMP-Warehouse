from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys
from time import monotonic, time_ns

import requests

from api_client import RateLimitedJsonClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common.bronze import BronzeStore  # noqa: E402


class EuroScrapas:
    """Store the raw API surface in bronze without refetching finished games."""

    API_LIVE_URL = "https://api-live.euroleague.net"
    LIVE_URL = "https://live.euroleague.net/api"
    LIVE_DATA_START_YEAR = 2007
    V2_PEOPLE_PAGE_SIZE = 1000
    # Just under a day, so a nightly run always re-checks season-level data.
    SEASON_LEVEL_REFRESH_HOURS = 20
    # Extra asks when a stored statistics or standings feed gets a worse answer.
    # About half of the answers to a fresh request are empty or a game behind.
    STALE_RETRIES = 8

    # name: (entity, statistic type, sort statistic). The team endpoints reject
    # the player sort statistics (400) and have no scoring or misc feed (404).
    V3_STATISTIC_SPECS = {
        "players_traditional": ("players", "traditional", "timePlayed"),
        "players_advanced": ("players", "advanced", "timePlayed"),
        "players_scoring": ("players", "scoring", "gamesPlayed"),
        "players_misc": ("players", "misc", "gamesPlayed"),
        "teams_traditional": ("teams", "traditional", None),
        "teams_advanced": ("teams", "advanced", None),
        "teams_opponents_traditional": ("teams", "opponentsTraditional", None),
        "teams_opponents_advanced": ("teams", "opponentsAdvanced", None),
    }
    V3_STATISTIC_MODES = ("perGame", "accumulated")
    STANDING_TYPES = (
        "basicstandings",
        "calendarstandings",
        "streaks",
        "aheadbehind",
        "margins",
    )
    LIVE_DATASETS = {
        "live_boxscores": "Boxscore",
        "play_by_play": "PlayByPlay",
        "shooting_charts": "Points",
        "live_evolution": "Evolution",
        "live_comparison": "Comparison",
        "live_scoring": "ShootingGraphic",
    }

    def __init__(
        self,
        competition,
        season_codes,
        datasets,
        euroleague_apis,
        failed_extractions_limit,
        game_code_start,
        datetime_now,
        year_today,
        refresh_current,
        request_interval,
        hot_hours=48,
    ):
        self.competition = competition
        self.competition_code = {"euroleague": "E", "eurocup": "U"}[competition]
        self.season_codes = season_codes
        self.datasets = set(datasets)
        self.live_apis = set(euroleague_apis)
        self.failed_extractions_limit = failed_extractions_limit
        self.game_code_start = game_code_start
        self.datetime_now = datetime_now
        self.current_season_code = f"{self.competition_code}{year_today}"
        self.refresh_current = refresh_current
        self.hot_hours = hot_hours
        self.now_utc = datetime.now(timezone.utc)
        self.hot = self.empty_hot_scope()
        self.changed_resources = []
        self.kept_resources = []
        self.stale_retries = self.STALE_RETRIES
        self.season_started_at = monotonic()
        self.run_started_at = self.season_started_at
        self.client = RateLimitedJsonClient(
            request_interval=request_interval,
            time_counter=self.get_time_counter,
        )
        self.failed_extractions = 0
        self.bronze_root = PROJECT_ROOT / "data" / "bronze"

    def implement_scrapping_process(self):
        """Run the requested primary and supplemental datasets."""
        if "seasons" in self.datasets:
            self.extract_seasons_catalog()

        for index, season_code in enumerate(self.season_codes):
            if index > 0:
                self.game_code_start = 1
            self.extract_season(season_code)

        total_minutes = round((monotonic() - self.run_started_at) / 60, 1)
        print(
            f"\nAll {len(self.season_codes)} season(s) finished  ---  "
            f"TotalTime: {total_minutes} min"
        )

    def activate_scope(self, scope):
        self.active_season_code = scope
        self.store = BronzeStore(self.bronze_root, self.competition, scope)

    def extract_seasons_catalog(self):
        self.activate_scope("_catalog")
        self.fetch_to_cache(
            source="v2.seasons",
            url=f"{self.API_LIVE_URL}/v2/competitions/{self.competition_code}/seasons",
            resource="v2/seasons",
            force=self.refresh_current,
        )

    def extract_season(self, season_code):
        self.activate_scope(season_code)
        self.announced_game_codes = set()
        self.season_started_at = monotonic()

        print(f"\nSeasonCode: {season_code}  ---  {self.get_time_counter()}")
        previous_games = self.store.read_json("v2/games")
        games = self.extract_game_list(season_code)
        if games is None:
            print(
                f"Skipping dependent datasets for {season_code}: game list unavailable."
                f"  ---  {self.get_time_counter()}"
            )
            return

        game_records = self.get_data_list(games)
        played_games = self.get_played_games(game_records)
        requested_games = [
            game
            for game in played_games
            if game["gameCode"] >= self.game_code_start
        ]
        self.hot = self.get_hot_scope(season_code, previous_games, played_games)
        if self.hot["any"]:
            rounds = ", ".join(f"{phase} {number}" for phase, number in sorted(self.hot["rounds"]))
            print(
                f"Recently played or newly completed games: refreshing mutable "
                f"season data (rounds: {rounds or 'none in group phase'})."
                f"  ---  {self.get_time_counter()}"
            )

        self.extract_v2_season_datasets(season_code, game_records)
        self.extract_v3_standings(season_code, played_games)
        self.extract_v3_season_stats(season_code, played_games)
        self.extract_game_stats(season_code, requested_games)
        self.extract_live_detail(season_code, requested_games)

        self.write_json(
            self.store.directory / "runs" / f"run_{self.datetime_now}.json",
            {
                "competition": self.competition,
                "season_code": season_code,
                "scheduled_games": len(game_records),
                "played_games": len(played_games),
                "requested_played_games": len(requested_games),
                "failed_requests_so_far": self.failed_extractions,
                "changed_resources": [
                    resource for resource in self.changed_resources
                    if resource.startswith(f"{season_code}/")
                ],
                "completed_at_utc": datetime.now(timezone.utc).isoformat(),
            },
        )

        print(
            f"SeasonCode: {season_code}  ---  ScheduledGames: {len(game_records)}"
            f"  ---  PlayedGames: {len(played_games)}"
            f"  ---  RequestedPlayedGames: {len(requested_games)}"
            f"  ---  {self.get_time_counter()}"
        )

    def extract_game_list(self, season_code):
        return self.fetch_to_cache(
            source="v2.game_lists",
            url=(
                f"{self.API_LIVE_URL}/v2/competitions/{self.competition_code}"
                f"/seasons/{season_code}/games"
            ),
            resource="v2/games",
            force=season_code == self.current_season_code,
        )

    def season_level_refresh_due(self, season_code):
        """Clubs, people, rosters and rounds change without games (signings,
        pre-season), so the current season re-checks them at least daily."""
        if season_code != self.current_season_code:
            return False
        state = self.read_json_file(self.store.directory / "refresh_state.json") or {}
        try:
            checked = datetime.fromisoformat(state["season_level_checked_at_utc"])
        except (KeyError, TypeError, ValueError):
            return True
        return self.now_utc - checked >= timedelta(hours=self.SEASON_LEVEL_REFRESH_HOURS)

    def extract_v2_season_datasets(self, season_code, game_records):
        daily_due = self.season_level_refresh_due(season_code)
        mutable_force = season_code == self.current_season_code and (
            self.refresh_current or self.hot["any"] or daily_due
        )

        clubs = None
        clubs_needed = "clubs" in self.datasets or "rosters" in self.datasets
        if clubs_needed:
            clubs = self.fetch_to_cache(
                source="v2.clubs",
                url=(
                    f"{self.API_LIVE_URL}/v2/competitions/{self.competition_code}"
                    f"/seasons/{season_code}/clubs"
                ),
                resource="v2/clubs",
                force=mutable_force,
            )

        if "season_people" in self.datasets:
            self.extract_v2_season_people(
                season_code=season_code,
                force=mutable_force,
            )

        if "rosters" in self.datasets and clubs is not None:
            for club in self.get_data_list(clubs):
                club_code = club.get("code")
                if not club_code:
                    continue
                self.fetch_to_cache(
                    source="v2.roster",
                    url=(
                        f"{self.API_LIVE_URL}/v2/competitions/{self.competition_code}"
                        f"/seasons/{season_code}/clubs/{club_code}/people"
                    ),
                    resource=f"v2/rosters/{club_code}",
                    force=mutable_force,
                )

        if "rounds" in self.datasets or "standings" in self.datasets:
            self.fetch_to_cache(
                source="v2.rounds",
                url=(
                    f"{self.API_LIVE_URL}/v2/competitions/{self.competition_code}"
                    f"/seasons/{season_code}/rounds"
                ),
                resource="v2/rounds",
                force=mutable_force,
            )

        if mutable_force:
            self.write_json(self.store.directory / "refresh_state.json", {
                "season_level_checked_at_utc": self.now_utc.isoformat(),
            })

    @classmethod
    def people_page_resource(cls, offset):
        return f"v2/season_people_pages/offset_{offset:06d}"

    def cached_people_pages(self):
        """Return the cached page payloads if they hold every row, else None."""
        first = self.store.read_json(self.people_page_resource(0))
        if not self.is_valid_data_payload(first):
            return None
        pages = [first]
        for offset in range(self.V2_PEOPLE_PAGE_SIZE, first["total"], self.V2_PEOPLE_PAGE_SIZE):
            page = self.store.read_json(self.people_page_resource(offset))
            if not self.is_valid_data_payload(page) or page["total"] != first["total"]:
                return None
            pages.append(page)
        if sum(len(page["data"]) for page in pages) != first["total"]:
            return None
        return pages

    def extract_v2_season_people(self, season_code, force):
        """Store every people page; the loader combines them.

        This endpoint defaults to 500 rows even when its ``total`` is larger, so
        every ``offset`` page is requested and the pages are checked for
        completeness. Each page is kept exactly as the API returned it.
        """
        source = "v2.season_people"
        url = (
            f"{self.API_LIVE_URL}/v2/competitions/{self.competition_code}"
            f"/seasons/{season_code}/people"
        )
        if not force:
            cached = self.cached_people_pages()
            if cached is not None:
                print(
                    f"[cached]  {source} ({cached[0]['total']} rows in {len(cached)} page(s))"
                    f"  ---  {self.get_time_counter()}"
                )
                return cached
            if self.store.exists(self.people_page_resource(0)):
                print(
                    f"[incomplete] {source} cache is partial; fetching all pages."
                    f"  ---  {self.get_time_counter()}"
                )

        first_page = self.fetch_to_cache(
            source=f"{source}.page",
            url=url,
            params={"offset": 0, "limit": self.V2_PEOPLE_PAGE_SIZE},
            resource=self.people_page_resource(0),
            force=True,
        )
        if not self.is_valid_data_payload(first_page):
            return None

        total = first_page["total"]
        pages = [first_page]
        for offset in range(self.V2_PEOPLE_PAGE_SIZE, total, self.V2_PEOPLE_PAGE_SIZE):
            page = self.fetch_to_cache(
                source=f"{source}.page",
                url=url,
                params={"offset": offset, "limit": self.V2_PEOPLE_PAGE_SIZE},
                resource=self.people_page_resource(offset),
                force=True,
            )
            if not self.is_valid_data_payload(page):
                return None
            if page["total"] != total:
                self.record_failure(
                    source,
                    url,
                    {"offset": offset, "limit": self.V2_PEOPLE_PAGE_SIZE},
                    ValueError(
                        "People endpoint total changed while its pages were being fetched"
                    ),
                )
                return None
            pages.append(page)

        received = sum(len(page["data"]) for page in pages)
        if received != total:
            self.record_failure(
                source,
                url,
                None,
                ValueError(f"Expected {total} people rows but received {received}"),
            )
            return None
        return pages

    def extract_v3_standings(self, season_code, played_games):
        if "standings" not in self.datasets:
            return

        mutable_force = (
            self.refresh_current and season_code == self.current_season_code
        )
        round_keys = sorted({
            (
                self.get_phase_code(game) or "unknown",
                game.get("round"),
            )
            for game in played_games
            if self.is_group_phase(game) and game.get("round") is not None
        })

        for phase_code, round_number in round_keys:
            round_force = mutable_force or (phase_code, round_number) in self.hot["rounds"]
            for standing_type in self.STANDING_TYPES:
                self.fetch_to_cache(
                    source=f"v3.standings.{standing_type}",
                    url=(
                        f"{self.API_LIVE_URL}/v3/competitions/{self.competition_code}"
                        f"/seasons/{season_code}/rounds/{round_number}/{standing_type}"
                    ),
                    resource=f"v3/standings/{phase_code}_{round_number}_{standing_type}",
                    force=round_force,
                    keep_if_worse=True,
                )

    def extract_v3_season_stats(self, season_code, played_games):
        if "season_stats" not in self.datasets or not played_games:
            return

        mutable_force = (
            self.refresh_current and season_code == self.current_season_code
        )
        phase_codes = ["all"] + sorted({
            phase_code
            for phase_code in (self.get_phase_code(game) for game in played_games)
            if phase_code
        })
        played_clubs = {
            phase_code: {
                ((game.get(side) or {}).get("club") or {}).get("code")
                for game in played_games
                if phase_code == "all" or self.get_phase_code(game) == phase_code
                for side in ("local", "road")
            } - {None}
            for phase_code in phase_codes
        }

        for name, (entity, statistic_type, sort_statistic) in self.V3_STATISTIC_SPECS.items():
            for statistic_mode in self.V3_STATISTIC_MODES:
                for phase_code in phase_codes:
                    params = {
                        "SeasonMode": "Single",
                        "SeasonCode": season_code,
                        "Statistic": sort_statistic,
                        "Limit": 1000,
                        "SortDirection": "descending",
                        "StatisticMode": statistic_mode,
                        "StatisticSortMode": statistic_mode,
                    }
                    if sort_statistic is None:
                        for sort_param in ("Statistic", "SortDirection", "StatisticSortMode"):
                            del params[sort_param]
                    if phase_code != "all":
                        params["PhaseTypeCode"] = phase_code
                    phase_force = mutable_force or (
                        self.hot["any"] if phase_code == "all"
                        else phase_code in self.hot["phases"]
                    )

                    self.fetch_to_cache(
                        source=f"v3.season_stats.{name}",
                        url=(
                            f"{self.API_LIVE_URL}/v3/competitions/{self.competition_code}"
                            f"/statistics/{entity}/{statistic_type}"
                        ),
                        params=params,
                        resource=f"v3/season_stats/{name}_{phase_code}_{statistic_mode}",
                        force=phase_force,
                        keep_if_worse=True,
                        min_clubs=len(played_clubs[phase_code]),
                    )

    def extract_game_stats(self, season_code, played_games):
        if "game_stats" not in self.datasets:
            return

        for game in played_games:
            game_code = game["gameCode"]
            self.print_game_progress(season_code, game)
            self.fetch_to_cache(
                source="v2.game_stats",
                url=(
                    f"{self.API_LIVE_URL}/v2/competitions/{self.competition_code}"
                    f"/seasons/{season_code}/games/{game_code}/stats"
                ),
                resource=f"v2/game_stats/{game_code}",
            )

    def extract_live_detail(self, season_code, played_games):
        if int(season_code[1:]) < self.LIVE_DATA_START_YEAR:
            print(
                f"Skipping live detail for {season_code}: coverage begins with "
                f"the {self.LIVE_DATA_START_YEAR} season."
                f"  ---  {self.get_time_counter()}"
            )
            return

        for dataset, endpoint in self.LIVE_DATASETS.items():
            if dataset not in self.datasets or endpoint not in self.live_apis:
                continue

            for game in played_games:
                game_code = game["gameCode"]
                self.print_game_progress(season_code, game)
                payload = self.fetch_to_cache(
                    source=f"live.{dataset}",
                    url=f"{self.LIVE_URL}/{endpoint}",
                    params={"gamecode": game_code, "seasoncode": season_code},
                    resource=f"live/{game_code}/{dataset}",
                )
                self.report_empty_live_payload(dataset, season_code, game_code, payload)

    @staticmethod
    def stats_feed_size(payload, accumulated):
        """(distinct clubs, total games played or None) of a v3 statistics list."""
        rows = (payload or {}).get("players") or (payload or {}).get("teams") or []
        clubs = {
            ((row.get("player") or {}).get("team") or {}).get("code")
            if "player" in row else (row.get("team") or {}).get("code")
            for row in rows
        }
        clubs.discard(None)
        games = sum(row.get("gamesPlayed") or 0 for row in rows) if accumulated else None
        return len(clubs), games

    @classmethod
    def worse_stats_answer(cls, stored, answer, resource):
        """Why ``answer`` is worse than the ``stored`` version, or None.

        Within a season a totals feed can only gain clubs and games played;
        less of either means the API answered stale. A per-game feed lists only
        clubs and players with more than half of the phase's games, so it can
        legitimately shrink: only an empty answer is refused there.
        """
        accumulated = resource.endswith("_accumulated")
        old_clubs, old_games = cls.stats_feed_size(stored, accumulated)
        new_clubs, new_games = cls.stats_feed_size(answer, accumulated)
        if accumulated:
            worse = new_clubs < old_clubs or new_games < old_games
        else:
            worse = new_clubs == 0 < old_clubs
        if worse:
            games = (f" / {new_games:g} games, stored version has {old_clubs} / {old_games:g}"
                     if accumulated else f", stored version has {old_clubs}")
            return f"API answered {new_clubs} clubs{games}"
        return None

    @staticmethod
    def worse_standings_answer(stored, answer):
        """Why a round-standings ``answer`` is worse than the ``stored`` version, or None.

        A round's standings are cumulative: clubs and games played only grow. Each
        of the five feeds is cached upstream on its own clock and can answer a
        game behind, also after a newer answer was already stored.
        """
        def size(payload):
            rows = (payload or {}).get("teams") or []
            clubs = {(row.get("club") or {}).get("code") for row in rows}
            clubs.discard(None)
            return len(clubs), sum(row.get("gamesPlayed") or 0 for row in rows)

        old_clubs, old_games = size(stored)
        new_clubs, new_games = size(answer)
        if new_clubs < old_clubs or new_games < old_games:
            return (f"API answered {new_clubs} clubs / {new_games:g} games, "
                    f"stored version has {old_clubs} / {old_games:g}")
        return None

    def fetch_to_cache(self, source, url, resource, params=None, force=False,
                       keep_if_worse=False, min_clubs=0):
        """Return the latest bronze payload when permitted, otherwise fetch and store it.

        With ``keep_if_worse`` (v3 season statistics and round standings), an answer
        smaller than the stored version is only logged in the manifest and the
        stored version is kept, because the API sometimes answers stale lists on
        game days. ``min_clubs`` is how many clubs have played in the scope: an
        answer listing fewer is stale too, which catches a per-game feed that is
        an older snapshot but not smaller than the stored version. Without a
        stored version, the last answer is stored anyway.
        """
        if not force and self.store.exists(resource):
            print(
                f"[cached]  {source} -> {resource}"
                f"  ---  {self.get_time_counter()}"
            )
            return self.store.read_json(resource)

        stored = (
            self.store.read_json(resource)
            if keep_if_worse and self.store.exists(resource) else None
        )
        checked = stored is not None or bool(min_clubs)
        attempts = 1 + (self.stale_retries if checked else 0)
        for attempt in range(1, attempts + 1):
            request_params = params
            if keep_if_worse:
                # The API sits behind a 2 hour CDN cache keyed on the full URL;
                # an unused parameter makes every request a cache miss.
                request_params = {**(params or {}), "_": time_ns()}
            print(
                f"[request] {source} -> {resource}"
                f"{f' (retry {attempt - 1}/{self.stale_retries})' if attempt > 1 else ''}"
                f"  ---  {self.get_time_counter()}"
            )
            try:
                payload, status_code, final_url, content = self.client.get_json(
                    url, params=request_params)
            except (requests.RequestException, ValueError) as error:
                response = getattr(error, "response", None)
                self.store.log({
                    "resource": resource, "url": url, "params": params,
                    "status_code": getattr(response, "status_code", None),
                    "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
                    "error": str(error), "stored_as": None,
                })
                self.record_failure(source, url, params, error)
                return None

            problem = None
            if stored is not None:
                if resource.startswith("v3/standings/"):
                    problem = self.worse_standings_answer(stored, payload)
                else:
                    problem = self.worse_stats_answer(stored, payload, resource)
            if not problem and min_clubs:
                clubs, _ = self.stats_feed_size(payload, False)
                if clubs < min_clubs:
                    problem = f"API answered {clubs} clubs, {min_clubs} have played"
            if not problem:
                break
            # Answers differ from request to request (several upstream
            # instances with different freshness), so asking again usually
            # reaches a complete one.
            print(
                f"[stale]   {resource}: {problem}"
                f"  ---  {self.get_time_counter()}"
            )

        if problem and stored is None:
            print(
                f"[stale]   {resource}: no stored version to keep, storing the last answer"
                f"  ---  {self.get_time_counter()}"
            )
        elif problem:
            self.store.log({
                "resource": resource, "url": final_url, "params": params,
                "status_code": status_code,
                "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
                "sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content),
                "stored_as": None, "rejected": problem,
            })
            self.kept_resources.append(f"{self.active_season_code}/{resource}")
            print(
                f"[kept]    {resource}: {problem} in all {attempts} attempt(s); "
                f"kept the stored version, refresh again later"
                f"  ---  {self.get_time_counter()}"
            )
            return stored

        changed = self.store.write(
            resource, content, url=final_url, params=params, status_code=status_code,
        )
        if changed:
            self.changed_resources.append(f"{self.active_season_code}/{resource}")
        label = "[saved]  " if changed else "[same]   "
        print(
            f"{label} {source} ({status_code}) -> {resource}"
            f"  ---  {self.get_time_counter()}"
        )
        return payload

    @staticmethod
    def empty_hot_scope():
        return {"any": False, "rounds": set(), "phases": set()}

    def get_hot_scope(self, season_code, previous_games, played_games):
        """Return current-season games whose mutable season data may be stale.

        A game is hot when it became played since the previous cached game list,
        or when it started within ``hot_hours``. Standings and v3 statistics can
        lag behind a final whistle, so recent rounds keep being refreshed for a
        while instead of being cached forever after their first fetch.
        """
        scope = self.empty_hot_scope()
        if season_code != self.current_season_code:
            return scope

        previously_played = {
            game["gameCode"]
            for game in self.get_played_games(self.get_data_list(previous_games))
        }
        cutoff = self.now_utc - timedelta(hours=self.hot_hours)
        for game in played_games:
            if game["gameCode"] in previously_played and not self.started_after(game, cutoff):
                continue
            scope["any"] = True
            phase_code = self.get_phase_code(game) or "unknown"
            scope["phases"].add(phase_code)
            if self.is_group_phase(game) and game.get("round") is not None:
                scope["rounds"].add((phase_code, game.get("round")))
        return scope

    @staticmethod
    def started_after(game, cutoff):
        value = game.get("utcDate")
        if not isinstance(value, str):
            return False
        try:
            started = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return False
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        return started >= cutoff

    def record_failure(self, source, url, params, error):
        self.failed_extractions += 1
        print(
            f"{source} failed: {error} --- URL: {url}"
            f"  ---  {self.get_time_counter()}"
        )

        failure_path = self.store.directory / "failures.jsonl"
        failure_path.parent.mkdir(parents=True, exist_ok=True)
        with failure_path.open("a", encoding="utf-8") as failure_file:
            failure_file.write(json.dumps({
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "source": source,
                "url": url,
                "params": params,
                "error": str(error),
            }) + "\n")

        if self.failed_extractions == self.failed_extractions_limit:
            print(
                "Failed-extraction warning threshold reached. Continuing with "
                "the remaining cache plan."
                f"  ---  {self.get_time_counter()}"
            )

    def report_empty_live_payload(self, dataset, season_code, game_code, payload):
        if dataset == "shooting_charts" and isinstance(payload, dict):
            if not payload.get("Rows"):
                print(
                    f"No shot rows returned for {season_code} game {game_code}; "
                    "the raw 200 response was retained."
                    f"  ---  {self.get_time_counter()}"
                )

    @staticmethod
    def get_data_list(payload):
        if isinstance(payload, dict) and isinstance(payload.get("data"), list):
            return payload["data"]
        if isinstance(payload, list):
            return payload
        return []

    @staticmethod
    def is_valid_data_payload(payload):
        return (
            isinstance(payload, dict)
            and isinstance(payload.get("data"), list)
            and isinstance(payload.get("total"), int)
            and payload["total"] >= 0
        )

    @staticmethod
    def get_played_games(games):
        return [
            game
            for game in games
            if isinstance(game, dict)
            and game.get("played") is True
            and isinstance(game.get("gameCode"), int)
        ]

    @staticmethod
    def get_phase_code(game):
        phase_type = game.get("phaseType")
        if isinstance(phase_type, dict):
            return phase_type.get("code")
        return game.get("phaseTypeCode")

    def print_game_progress(self, season_code, game):
        """Print the one-line game monitor used by the original extractor."""
        game_code = game["gameCode"]
        if game_code in self.announced_game_codes:
            return

        phase_type = game.get("phaseType")
        if isinstance(phase_type, dict):
            phase = phase_type.get("name") or phase_type.get("code") or "Unknown"
        else:
            phase = game.get("phaseTypeCode") or "Unknown"

        round_number = game.get("round")
        if isinstance(round_number, int):
            round_display = f"{round_number:02d}"
        else:
            round_display = str(round_number or "Unknown")

        print(
            f"SeasonCode: {season_code}  ---  Phase: {phase}  ---  "
            f"Round: {round_display}  ---  GameCode: {game_code:03d}  ---  "
            f"{self.get_time_counter()}"
        )
        self.announced_game_codes.add(game_code)

    def get_time_counter(self):
        """Return the elapsed time of the active season and of the whole run."""
        now = monotonic()
        season_minutes = round((now - self.season_started_at) / 60, 1)
        total_minutes = round((now - self.run_started_at) / 60, 1)
        return f"TimeCounter: {season_minutes} min  ---  TotalTime: {total_minutes} min"

    @staticmethod
    def is_group_phase(game):
        phase_type = game.get("phaseType")
        return isinstance(phase_type, dict) and phase_type.get("isGroupPhase") is True

    @staticmethod
    def read_json_file(path):
        try:
            with path.open(encoding="utf-8") as input_file:
                return json.load(input_file)
        except (OSError, ValueError):
            return None

    @staticmethod
    def write_json(path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = path.with_suffix(f"{path.suffix}.tmp")
        with temporary_path.open("w", encoding="utf-8") as output_file:
            json.dump(payload, output_file, ensure_ascii=False)
        temporary_path.replace(path)
