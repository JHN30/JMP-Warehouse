from argparse import ArgumentParser
from datetime import date, datetime
from itertools import chain


def get_datetime_info():
    """Return a log timestamp and the start year of the current season."""
    datetime_now = datetime.now().strftime("%Y%m%d_%H%M%S")
    year_today = date.today().year
    if date.today().month not in (9, 10, 11, 12):
        year_today -= 1
    return datetime_now, year_today


class SimpleLogger:
    """Mirror stdout to the terminal and one log file."""

    def __init__(self, out1, out2):
        self.out1 = out1
        self.out2 = out2

    def write(self, *args, **kwargs):
        self.out1.write(*args, **kwargs)
        self.out2.write(*args, **kwargs)

    def flush(self):
        self.out1.flush()
        self.out2.flush()


class ConfigParser(ArgumentParser):
    """Parse the extraction scope without coupling it to an API host."""

    DEFAULT_DATASETS = [
        "seasons",
        "game_lists",
        "clubs",
        "rosters",
        "rounds",
        "season_people",
        "season_stats",
        "standings",
        "game_stats",
        "play_by_play",
        "shooting_charts",
    ]
    # Live API endpoints whose content is covered by v2 game data, play-by-play
    # or shots (verified on every E2025 game). Requested only when named with -ds.
    OPTIONAL_DATASETS = [
        "live_boxscores",
        "live_evolution",
        "live_comparison",
        "live_scoring",
    ]

    LIVE_DATASET_TO_API = {
        "live_boxscores": "Boxscore",
        "play_by_play": "PlayByPlay",
        "shooting_charts": "Points",
        "live_evolution": "Evolution",
        "live_comparison": "Comparison",
        "live_scoring": "ShootingGraphic",
    }
    LIVE_API_ALIASES = {
        "PlaybyPlay": "PlayByPlay",
    }

    def __init__(self, year_today):
        super().__init__(
            prog="scrapper",
            description=(
                "cache EuroLeague/EuroCup data from v2, v3, and supplemental "
                "live endpoints"
            ),
        )
        self.year_today = year_today
        self.valid_euroleague_apis = list(self.LIVE_DATASET_TO_API.values())
        self.valid_datasets = ["all"] + self.DEFAULT_DATASETS + self.OPTIONAL_DATASETS
        self.competition = None
        self.season_codes = None
        self.datasets = None
        self.euroleague_apis = None
        self.failed_extractions_limit = None
        self.game_code_start = None
        self.refresh_current = None
        self.request_interval = None
        self.hot_hours = None
        self.summary_file = None

    def set_arguments(self):
        self.add_argument(
            "-cp",
            "--competition",
            type=str,
            nargs="?",
            default="euroleague",
            choices=["euroleague", "eurocup"],
            help="The competition to extract.",
        )
        self.add_argument(
            "-sc",
            "--season_code",
            type=str,
            nargs="+",
            default=[str(self.year_today)],
            help=(
                "Season start years or inclusive ranges, for example 2024 or "
                "2022-2025. Valid years run from 2000 to the current season."
            ),
        )
        self.add_argument(
            "-ds",
            "--dataset",
            type=str,
            nargs="+",
            default=["all"],
            choices=self.valid_datasets,
            help=(
                "Datasets to cache. The default 'all' includes v2/v3 primary "
                "data plus live play-by-play and shots. The redundant live API "
                "live_boxscores, live_evolution, live_comparison and "
                "live_scoring are fetched only when named explicitly and are "
                "archived in bronze only (not loaded into PostgreSQL)."
            ),
        )
        self.add_argument(
            "-api",
            "--euroleague_api",
            type=str,
            nargs="+",
            default=self.valid_euroleague_apis,
            help=(
                "Optional subset of supplemental live APIs. Header is not "
                "requested because v2 game lists supersede it."
            ),
        )
        self.add_argument(
            "-fel",
            "--failed_extractions_limit",
            type=int,
            nargs="?",
            default=500,
            help=(
                "Warning threshold for failed requests. Failures are recorded "
                "but never decide where a season ends."
            ),
        )
        self.add_argument(
            "-gcs",
            "--game_code_start",
            type=int,
            nargs="?",
            default=1,
            help=(
                "Only process game codes greater than or equal to this value "
                "for the first requested season."
            ),
        )
        self.add_argument(
            "--refresh-current",
            action="store_true",
            help=(
                "Refresh mutable season-level datasets for the current season. "
                "Completed game-detail files remain immutable."
            ),
        )
        self.add_argument(
            "--request-interval",
            type=float,
            default=2.5,
            help=(
                "Minimum seconds between upstream requests. The safe default "
                "is 2.5 seconds."
            ),
        )
        self.add_argument(
            "--hot-hours",
            type=float,
            default=48,
            help=(
                "Current-season standings, statistics and rosters are refreshed "
                "while a game played within this many hours (or newly completed) "
                "affects them. Default: 48."
            ),
        )
        self.add_argument(
            "--summary-file",
            type=str,
            default=None,
            help=(
                "Optional JSON file for the run summary (changed resources and "
                "failed requests), used by the pipeline to skip unchanged runs."
            ),
        )
        return self.parse_args()

    def parse_arguments(self, args):
        """Validate and store the arguments; describe() summarizes them."""
        self.competition = args.competition

        try:
            standalone_years = [int(sc) for sc in args.season_code if "-" not in sc]
            range_args = [sc for sc in args.season_code if "-" in sc]
            ranges = [
                list(range(start, end + 1))
                for start, end in (map(int, sc.split("-")) for sc in range_args)
            ]
            years = sorted(set(chain.from_iterable([standalone_years] + ranges)))
        except ValueError as error:
            self.error(f"Invalid season code: {error}")

        competition_letter = {"euroleague": "E", "eurocup": "U"}[self.competition]
        self.current_season_code = f"{competition_letter}{self.year_today}"
        self.season_codes = [
            f"{competition_letter}{year}"
            for year in years
            if year in range(2000, self.year_today + 1)
        ]
        if not self.season_codes:
            self.error(
                f"season_code must be in the range 2000 to {self.year_today}"
            )

        requested = list(dict.fromkeys(args.dataset))
        self.datasets = (
            self.DEFAULT_DATASETS + [name for name in requested if name != "all"
                                     and name not in self.DEFAULT_DATASETS]
            if "all" in requested
            else requested
        )

        self.euroleague_apis = list(dict.fromkeys(
            self.LIVE_API_ALIASES.get(api, api)
            for api in args.euroleague_api
            if self.LIVE_API_ALIASES.get(api, api) in self.valid_euroleague_apis
        ))

        self.failed_extractions_limit = args.failed_extractions_limit
        if self.failed_extractions_limit <= 0:
            self.error("failed_extractions_limit must be a positive integer")

        self.game_code_start = args.game_code_start
        if self.game_code_start <= 0:
            self.error("game_code_start must be a positive integer")

        self.request_interval = args.request_interval
        if self.request_interval < 0:
            self.error("request_interval must be zero or greater")

        self.refresh_current = args.refresh_current

        self.hot_hours = getattr(args, "hot_hours", 48)
        if self.hot_hours < 0:
            self.error("hot_hours must be zero or greater")

        self.summary_file = getattr(args, "summary_file", None)

    @property
    def live_endpoints(self):
        """Live API endpoints that will really be called: dataset selected and API allowed."""
        return [
            api for dataset, api in self.LIVE_DATASET_TO_API.items()
            if dataset in self.datasets and api in self.euroleague_apis
        ]

    def describe(self):
        """Short run summary with only the settings that affect this run."""
        seasons = self.season_codes
        season_text = (
            f"{seasons[0]}-{seasons[-1]} ({len(seasons)} seasons)"
            if len(seasons) > 2 and len(seasons) == int(seasons[-1][1:]) - int(seasons[0][1:]) + 1
            else ", ".join(seasons)
        )
        lines = [
            f"competition: {self.competition}",
            f"seasons: {season_text}",
            f"datasets: {', '.join(self.datasets)}",
            "live endpoints: " + (
                f"{', '.join(self.live_endpoints)} (played games, seasons from 2007)"
                if self.live_endpoints else "none"
            ),
            f"request interval: {self.request_interval} s",
        ]
        if self.current_season_code in seasons:
            lines.append(
                f"current season {self.current_season_code}: refreshed for games played in "
                f"the last {self.hot_hours:g} h" + (
                    "; --refresh-current forces all mutable data" if self.refresh_current else ""
                )
            )
        if self.game_code_start != 1:
            lines.append(f"first season starts at game code {self.game_code_start}")
        if self.failed_extractions_limit != 500:
            lines.append(f"failure warning after {self.failed_extractions_limit} failed requests")
        return lines
