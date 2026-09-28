"""Bronze layer: exact API response bytes, gzipped, never edited.

Layout (one directory per competition and scope; scope is a season code such
as E2025, or _catalog for competition-wide resources)::

    data/bronze/<competition>/<scope>/<resource>/<fetched_at>_<sha16>.json.gz
    data/bronze/<competition>/<scope>/manifest.jsonl

<resource> is a logical path such as ``v2/games`` or ``live/12/play_by_play``.
A new version file is written only when the response bytes differ from the
latest stored version; every request, stored or not, is appended to
``manifest.jsonl`` (url, params, HTTP status, fetched_at, sha256, bytes).
Readers always get the latest version, so refreshes never overwrite history.
"""

import gzip
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


SUFFIX = ".json.gz"


def utc_stamp(moment=None):
    moment = moment or datetime.now(timezone.utc)
    return moment.strftime("%Y%m%dT%H%M%S%fZ")


class BronzeStore:
    def __init__(self, bronze_root, competition, scope, on_read=None):
        self.directory = Path(bronze_root) / competition / scope
        self.scope = scope
        self.on_read = on_read

    # --- reading -----------------------------------------------------------
    def versions(self, resource):
        folder = self.directory / resource
        if not folder.is_dir():
            return []
        return sorted(path for path in folder.iterdir() if path.name.endswith(SUFFIX))

    def latest_path(self, resource):
        versions = self.versions(resource)
        return versions[-1] if versions else None

    def exists(self, resource):
        return self.latest_path(resource) is not None

    def read_bytes(self, resource):
        path = self.latest_path(resource)
        if path is None:
            raise FileNotFoundError(f"No bronze version of {self.scope}/{resource}")
        content = gzip.decompress(path.read_bytes())
        if self.on_read is not None:
            self.on_read(path)
        return content

    def read_json(self, resource, default=None):
        if not self.exists(resource):
            return default
        try:
            return json.loads(self.read_bytes(resource).decode("utf-8"))
        except (OSError, ValueError, EOFError):
            return default

    def resources(self, pattern="**"):
        """Logical resources below this scope matching a glob such as ``live/*/shots``."""
        if not self.directory.is_dir():
            return []
        found = {
            path.parent.relative_to(self.directory).as_posix()
            for path in self.directory.glob(f"{pattern}/*{SUFFIX}")
        }
        return sorted(found)

    # --- writing -----------------------------------------------------------
    def write(self, resource, content, url=None, params=None, status_code=None,
              fetched_at=None):
        """Store ``content`` unless identical to the latest version.

        Returns True when a new version was written (the data changed).
        """
        fetched_at = fetched_at or datetime.now(timezone.utc)
        sha = hashlib.sha256(content).hexdigest()
        latest = self.latest_path(resource)
        changed = latest is None or not latest.name.endswith(f"_{sha[:16]}{SUFFIX}")
        stored_as = None
        if changed:
            folder = self.directory / resource
            folder.mkdir(parents=True, exist_ok=True)
            target = folder / f"{utc_stamp(fetched_at)}_{sha[:16]}{SUFFIX}"
            temporary = target.with_name(target.name + ".tmp")
            temporary.write_bytes(gzip.compress(content, compresslevel=6))
            temporary.replace(target)
            stored_as = target.name
        self.log({
            "resource": resource, "url": url, "params": params,
            "status_code": status_code, "fetched_at_utc": fetched_at.isoformat(),
            "sha256": sha, "bytes": len(content), "stored_as": stored_as,
        })
        return changed

    def log(self, record):
        self.directory.mkdir(parents=True, exist_ok=True)
        with (self.directory / "manifest.jsonl").open("a", encoding="utf-8") as manifest:
            manifest.write(json.dumps(record, ensure_ascii=False) + "\n")


def available_scopes(bronze_root, competition):
    directory = Path(bronze_root) / competition
    if not directory.is_dir():
        return []
    return sorted(entry.name for entry in directory.iterdir() if entry.is_dir())
