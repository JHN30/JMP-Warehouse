from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from time import monotonic, sleep

import requests


class RateLimitedJsonClient:
    """Small JSON client that shares one request budget across every host."""

    def __init__(
        self,
        request_interval=2.5,
        timeout=30,
        max_retries=2,
        time_counter=None,
    ):
        self.request_interval = request_interval
        self.timeout = timeout
        self.max_retries = max_retries
        self.time_counter = time_counter
        self.last_request_started_at = None
        self.session = requests.Session()

    def get_json(self, url, params=None):
        """Return payload, status code, final URL and the exact response bytes.

        Raise on final failure.
        """
        last_error = None

        for attempt in range(self.max_retries + 1):
            self.wait_for_request_slot()
            try:
                response = self.session.get(url, params=params, timeout=self.timeout)
            except requests.RequestException as error:
                last_error = error
                if attempt == self.max_retries:
                    raise
                self.sleep_before_retry(attempt)
                continue

            if response.status_code == 429:
                last_error = requests.HTTPError(
                    "HTTP 429 rate limit", response=response
                )
                if attempt == self.max_retries:
                    response.raise_for_status()
                retry_after = self.get_retry_after_seconds(response)
                print(
                    f"HTTP 429 received. Respecting Retry-After for "
                    f"{retry_after:.0f} seconds.{self.get_time_suffix()}"
                )
                sleep(retry_after)
                continue

            if response.status_code >= 500:
                last_error = requests.HTTPError(
                    f"HTTP {response.status_code}", response=response
                )
                if attempt == self.max_retries:
                    response.raise_for_status()
                self.sleep_before_retry(attempt)
                continue

            response.raise_for_status()
            try:
                return response.json(), response.status_code, response.url, response.content
            except ValueError:
                raise ValueError(
                    f"Expected JSON but received an invalid response from {response.url}"
                )

        raise last_error

    def wait_for_request_slot(self):
        if self.last_request_started_at is not None:
            elapsed = monotonic() - self.last_request_started_at
            sleep(max(0, self.request_interval - elapsed))
        self.last_request_started_at = monotonic()

    def get_time_suffix(self):
        if self.time_counter is None:
            return ""
        return f"  ---  {self.time_counter()}"

    @staticmethod
    def sleep_before_retry(attempt):
        sleep(min(60, 2 ** (attempt + 1)))

    @staticmethod
    def get_retry_after_seconds(response):
        retry_after = response.headers.get("Retry-After")
        if retry_after is None:
            return 300
        try:
            return max(1, float(retry_after))
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(retry_after)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=timezone.utc)
                return max(
                    1,
                    (retry_at - datetime.now(timezone.utc)).total_seconds(),
                )
            except (TypeError, ValueError):
                return 300
