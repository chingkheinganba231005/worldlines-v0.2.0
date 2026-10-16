"""Bounded, verified access to the official GDELT 2.0 event stream.

WORLDLINE reads one stream in two official encodings:

* daily files   https://data.gdeltproject.org/events/YYYYMMDD.export.CSV.zip      (58 columns)
* 15-minute     https://data.gdeltproject.org/gdeltv2/YYYYMMDDHHMMSS.export.CSV.zip (61 columns)

On 2026-10-13 we verified that the daily file is exactly the union of the 96
fifteen-minute exports of that UTC day (116,603 identical GLOBALEVENTIDs), so
history (daily files) and live monitoring (15-minute files) are one dataset.

Only metadata is downloaded. Linked news articles are never fetched.
"""
from __future__ import annotations

import base64
import hashlib
import io
import random
import re
import time
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

HOST = "data.gdeltproject.org"
DAILY_PREFIX = f"https://{HOST}/events/"
V2_PREFIX = f"https://{HOST}/gdeltv2/"
USER_AGENT = "WORLDLINE/0.2 (+https://github.com/chingkheinganba231005/worldlines-v0.2.0; bounded metadata research)"
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
MAX_EXPANSION_RATIO = 40
ALLOWED_PATHS = re.compile(
    r"/(?:events/(?:index\.html|md5sums|filesizes|[0-9]{8}\.export\.CSV\.zip)"
    r"|gdeltv2/(?:lastupdate\.txt|[0-9]{14}\.export\.CSV\.zip))")


class ProviderError(RuntimeError):
    """The provider could not deliver valid data. Never silently substituted."""


class NotPublished(ProviderError):
    """HTTP 404: the requested archive does not exist (yet, or ever)."""


@dataclass(frozen=True)
class Layout:
    """Zero-based column positions; the first 35 columns are shared by both encodings."""
    name: str
    columns: int
    action_type: int
    action_country: int
    action_lat: int
    action_lon: int
    date_added: int
    source_url: int


DAILY = Layout("gdelt-events-daily-58", 58, 49, 51, 53, 54, 56, 57)
FIFTEEN = Layout("gdelt-events-15min-61", 61, 51, 53, 56, 57, 59, 60)
ID, SQLDATE, ACTOR1_COUNTRY, ACTOR2_COUNTRY = 0, 1, 7, 17
IS_ROOT, EVENT_CODE, BASE_CODE, ROOT_CODE, QUAD, GOLDSTEIN = 25, 26, 27, 28, 29, 30
NUM_MENTIONS, NUM_SOURCES, NUM_ARTICLES, AVG_TONE = 31, 32, 33, 34


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def daily_url(day: date) -> str:
    return f"{DAILY_PREFIX}{day:%Y%m%d}.export.CSV.zip"


def slot_url(stamp: datetime) -> str:
    return f"{V2_PREFIX}{stamp:%Y%m%d%H%M%S}.export.CSV.zip"


def day_slots(day: date) -> list[datetime]:
    start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    return [start + timedelta(minutes=15 * i) for i in range(96)]


def validate_url(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.netloc != HOST or parts.query or parts.fragment or not ALLOWED_PATHS.fullmatch(parts.path):
        raise ProviderError(f"refusing non-official or unsupported GDELT URL: {url}")


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        raise ProviderError("redirect refused; only direct official archive URLs are accepted")


class Client:
    """HTTPS client with byte limits, finite jittered retries and a circuit breaker."""

    def __init__(self, *, timeout: float = 60, attempts: int = 4, sleeper=time.sleep, opener=None):
        self.timeout = timeout
        self.attempts = min(max(attempts, 1), 6)
        self.sleeper = sleeper
        self.opener = opener or build_opener(_NoRedirect())
        self.consecutive_failures = 0
        self.open_until = 0.0

    def fetch(self, url: str) -> bytes:
        return self.fetch_with_meta(url)[0]

    def fetch_with_meta(self, url: str) -> tuple[bytes, dict]:
        """Download and verify transfer integrity against the storage layer's own MD5.

        GDELT is served from Google Cloud Storage, which returns the stored object's MD5
        (x-goog-hash / ETag). A mismatch means a corrupted transfer and is retried; it is
        distinct from disagreement with GDELT's separately published md5sums list.
        """
        validate_url(url)
        if time.monotonic() < self.open_until:
            raise ProviderError("provider circuit open after repeated failures; retry later")
        last: Exception | None = None
        for attempt in range(self.attempts):
            try:
                request = Request(url, headers={"User-Agent": USER_AGENT})
                with self.opener.open(request, timeout=self.timeout) as response:
                    validate_url(response.geturl())
                    declared = response.headers.get("Content-Length")
                    if declared and int(declared) > MAX_ARCHIVE_BYTES:
                        raise ProviderError("archive exceeds download byte limit")
                    payload = response.read(MAX_ARCHIVE_BYTES + 1)
                    served = served_md5(response.headers)
                if len(payload) > MAX_ARCHIVE_BYTES:
                    raise ProviderError("archive exceeds download byte limit")
                computed = hashlib.md5(payload).hexdigest()
                if served and served != computed:
                    last = ProviderError(f"transfer integrity failure for {url}: served MD5 {served}, received {computed}")
                    if attempt + 1 < self.attempts:
                        self.sleeper(min(20.0, 1.0 * 2 ** attempt + random.random()))
                    continue
                self.consecutive_failures = 0
                return payload, {"served_md5": served, "transfer_verified": bool(served)}
            except HTTPError as exc:
                if exc.code == 404:
                    raise NotPublished(f"not published: {url}") from exc
                last = exc
                if exc.code != 429 and exc.code < 500:
                    break
            except (URLError, TimeoutError, OSError) as exc:
                last = exc
            if attempt + 1 < self.attempts:
                self.sleeper(min(20.0, 1.0 * 2 ** attempt + random.random()))
        self.consecutive_failures += 1
        if self.consecutive_failures >= 3:
            self.open_until = time.monotonic() + 120
        raise ProviderError(f"GDELT request failed after retries: {type(last).__name__}: {last}") from last

    def latest_slot(self) -> datetime:
        """Newest published 15-minute slot according to the official manifest."""
        text = self.fetch(V2_PREFIX + "lastupdate.txt").decode("ascii", errors="strict")
        for line in text.splitlines():
            parts = line.split()
            if len(parts) == 3 and parts[2].endswith(".export.CSV.zip"):
                stamp = re.search(r"([0-9]{14})\.export\.CSV\.zip$", parts[2])
                if stamp:
                    return datetime.strptime(stamp.group(1), "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
        raise ProviderError("lastupdate manifest lists no events export")

    def daily_md5s(self) -> dict[str, str]:
        """Official MD5 checksums of daily files, keyed by YYYYMMDD."""
        text = self.fetch(DAILY_PREFIX + "md5sums").decode("ascii", errors="replace")
        sums = {}
        for line in text.splitlines():
            match = re.fullmatch(r"([0-9a-f]{32})\s+([0-9]{8})\.export\.CSV\.zip", line.strip())
            if match:
                sums[match.group(2)] = match.group(1)
        return sums


def served_md5(headers) -> str | None:
    """MD5 of the stored object as declared by the storage layer, if any."""
    # GCS sends one x-goog-hash header per algorithm; proxies may legally fold them into one comma-separated value.
    for value in headers.get_all("x-goog-hash") or []:
        for part in value.split(","):
            part = part.strip()
            if part.startswith("md5="):
                try:
                    return base64.b64decode(part[4:], validate=True).hex()
                except ValueError:
                    return None
    etag = (headers.get("ETag") or "").strip('"')
    return etag if re.fullmatch(r"[0-9a-f]{32}", etag) else None


def unpack(payload: bytes) -> bytes:
    """Return the single TSV member of an official archive, with expansion limits."""
    if len(payload) > MAX_ARCHIVE_BYTES:
        raise ProviderError("archive exceeds byte limit")
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            members = archive.infolist()
            if len(members) != 1:
                raise ProviderError("expected exactly one member in archive")
            member = members[0]
            if not re.fullmatch(r"[0-9]{8}(?:[0-9]{6})?\.export\.CSV", member.filename):
                raise ProviderError(f"unexpected archive member name: {member.filename!r}")
            if member.file_size > MAX_UNCOMPRESSED_BYTES or member.file_size > max(member.compress_size, 1) * MAX_EXPANSION_RATIO:
                raise ProviderError("archive expansion limit exceeded")
            with archive.open(member) as stream:
                data = stream.read(MAX_UNCOMPRESSED_BYTES + 1)
            if len(data) > MAX_UNCOMPRESSED_BYTES:
                raise ProviderError("archive expanded beyond limit")
            return data
    except ProviderError:
        raise
    except (zipfile.BadZipFile, RuntimeError, EOFError) as exc:
        raise ProviderError("invalid, truncated or encrypted archive") from exc


def checksums(payload: bytes) -> dict[str, str | int]:
    return {"md5": hashlib.md5(payload).hexdigest(), "sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload)}


def rows(tsv: bytes, layout: Layout):
    """Yield raw field lists. Rows with the wrong width are yielded as None (counted, not fatal)."""
    text = tsv.decode("utf-8", errors="replace")
    for line in text.split("\n"):
        if not line:
            continue
        fields = line.rstrip("\r").split("\t")
        yield fields if len(fields) == layout.columns else None
