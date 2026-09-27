from utils import get_datetime_info, SimpleLogger, ConfigParser
from scrapper import EuroScrapas
from common.db import log_directory  # project root is put on sys.path by scrapper
import json
import sys
import warnings
warnings.filterwarnings("ignore")


def main():
    
    # get datetime info
    datetime_now, year_today = get_datetime_info()

    # create a simple logfile
    log_path = log_directory("api_requests") / f"logfile_{datetime_now}"
    sys.stdout = SimpleLogger(open(log_path, "w", encoding="utf-8"), sys.stdout)
 
    # parse command line arguments
    config_parser = ConfigParser(year_today)
    args = config_parser.set_arguments()
    config_parser.parse_arguments(args)
    print("RUN SETTINGS")
    for line in config_parser.describe():
        print(f"  {line}")
    
    # get info from parsed arguments
    competition = config_parser.competition
    season_codes = config_parser.season_codes
    datasets = config_parser.datasets
    euroleague_apis = config_parser.euroleague_apis
    failed_extractions_limit = config_parser.failed_extractions_limit
    game_code_start = config_parser.game_code_start
    refresh_current = config_parser.refresh_current
    request_interval = config_parser.request_interval
    
    # initialize EuroScrapas and implement scrapping process
    euro_scrapas = EuroScrapas(
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
        hot_hours=config_parser.hot_hours,
    )
    try:
        euro_scrapas.implement_scrapping_process()
    except KeyboardInterrupt:
        print(
            "\nExtraction interrupted. Cached raw responses and the manifest "
            "were saved after each completed request. Re-run the same command "
            "to continue; existing game-level cache files will be skipped."
        )
        return 130

    print(
        f"\nChanged resources: {len(euro_scrapas.changed_resources)}"
        f"  ---  Failed requests: {euro_scrapas.failed_extractions}"
        f"  ---  Stats feeds kept from an earlier fetch: {len(euro_scrapas.kept_resources)}"
    )
    if config_parser.summary_file:
        with open(config_parser.summary_file, "w", encoding="utf-8") as summary:
            json.dump({
                "competition": competition,
                "season_codes": season_codes,
                "changed_resources": euro_scrapas.changed_resources,
                "failed_requests": euro_scrapas.failed_extractions,
                "kept_resources": euro_scrapas.kept_resources,
            }, summary, indent=1)

    return 0


if __name__ == '__main__':
    
    sys.exit(main())
