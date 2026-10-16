import base64
import hashlib
import io
import zipfile
from datetime import date, datetime, timezone
from email.message import Message
from urllib.error import HTTPError

import pytest

from synthetic import archive
from worldline import gdelt
from worldline.gdelt import Client, NotPublished, ProviderError


class FakeResponse:
    def __init__(self, url: str, payload: bytes, headers: dict[str, str] | None = None, final_url: str | None = None):
        self.url, self.payload, self.final_url = url, payload, final_url or url
        self.headers = Message()
        for key, value in (headers or {}).items():
            self.headers[key] = value

    def geturl(self):
        return self.final_url

    def read(self, limit=-1):
        return self.payload if limit < 0 else self.payload[:limit]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeOpener:
    """Serves a scripted sequence of responses (or exceptions) per URL."""

    def __init__(self, script: dict[str, list]):
        self.script = {url: list(items) for url, items in script.items()}
        self.calls: list[str] = []

    def open(self, request, timeout=None):
        url = request.full_url
        self.calls.append(url)
        item = self.script[url].pop(0) if len(self.script[url]) > 1 else self.script[url][0]
        if isinstance(item, Exception):
            raise item
        return item


def goog_md5(payload: bytes) -> str:
    return "crc32c=AAAAAA==,md5=" + base64.b64encode(hashlib.md5(payload).digest()).decode()


DAY_URL = "https://data.gdeltproject.org/events/20250101.export.CSV.zip"


def test_urls_and_slots():
    assert gdelt.daily_url(date(2025, 1, 1)) == DAY_URL
    stamp = datetime(2025, 1, 1, 23, 45, tzinfo=timezone.utc)
    assert gdelt.slot_url(stamp) == "https://data.gdeltproject.org/gdeltv2/20250101234500.export.CSV.zip"
    slots = gdelt.day_slots(date(2025, 1, 1))
    assert len(slots) == 96 and slots[0].hour == 0 and slots[-1] == stamp


@pytest.mark.parametrize("url", [
    "http://data.gdeltproject.org/events/20250101.export.CSV.zip",
    "https://data.gdeltproject.org.evil.example/events/20250101.export.CSV.zip",
    "https://data.gdeltproject.org/events/20250101.export.CSV.zip?x=1",
    "https://data.gdeltproject.org/gdeltv2/20250101.mentions.CSV.zip",
    "https://data.gdeltproject.org/events/../etc/passwd",
])
def test_validate_url_refuses_anything_but_official_archives(url):
    with pytest.raises(ProviderError):
        gdelt.validate_url(url)


def test_served_md5_reads_storage_hash_and_etag():
    payload = b"hello"
    folded = Message()
    folded["x-goog-hash"] = goog_md5(payload)  # "crc32c=...,md5=..." in one header
    assert gdelt.served_md5(folded) == hashlib.md5(payload).hexdigest()
    separate = Message()
    separate["x-goog-hash"] = "crc32c=AAAAAA=="
    separate["x-goog-hash"] = "md5=" + base64.b64encode(hashlib.md5(payload).digest()).decode()
    assert gdelt.served_md5(separate) == hashlib.md5(payload).hexdigest()
    etag_only = Message()
    etag_only["ETag"] = '"' + hashlib.md5(payload).hexdigest() + '"'
    assert gdelt.served_md5(etag_only) == hashlib.md5(payload).hexdigest()
    composite = Message()
    composite["ETag"] = '"abc-2"'  # multipart upload: not an MD5
    assert gdelt.served_md5(composite) is None


def test_fetch_verifies_transfer_and_retries_corruption():
    good = archive("20250101.export.CSV", b"a\tb\n")
    corrupt = good[:-1] + bytes([good[-1] ^ 1])
    headers = {"x-goog-hash": goog_md5(good)}
    opener = FakeOpener({DAY_URL: [FakeResponse(DAY_URL, corrupt, headers), FakeResponse(DAY_URL, good, headers)]})
    client = Client(opener=opener, sleeper=lambda s: None)
    payload, meta = client.fetch_with_meta(DAY_URL)
    assert payload == good and meta["transfer_verified"] is True
    assert len(opener.calls) == 2


def test_fetch_gives_up_on_persistent_corruption():
    good = archive("20250101.export.CSV", b"a\tb\n")
    opener = FakeOpener({DAY_URL: [FakeResponse(DAY_URL, good + b"x", {"x-goog-hash": goog_md5(good)})]})
    with pytest.raises(ProviderError, match="integrity"):
        Client(opener=opener, attempts=3, sleeper=lambda s: None).fetch(DAY_URL)
    assert len(opener.calls) == 3


def test_not_published_and_circuit_breaker():
    missing = HTTPError(DAY_URL, 404, "Not Found", Message(), None)
    with pytest.raises(NotPublished):
        Client(opener=FakeOpener({DAY_URL: [missing]}), sleeper=lambda s: None).fetch(DAY_URL)
    failing = Client(opener=FakeOpener({DAY_URL: [HTTPError(DAY_URL, 503, "Busy", Message(), None)]}),
                     attempts=2, sleeper=lambda s: None)
    for _ in range(3):
        with pytest.raises(ProviderError, match="after retries"):
            failing.fetch(DAY_URL)
    with pytest.raises(ProviderError, match="circuit open"):
        failing.fetch(DAY_URL)


def test_redirect_target_is_validated():
    payload = archive("20250101.export.CSV", b"x\n")
    response = FakeResponse(DAY_URL, payload, final_url="https://mirror.example.com/20250101.export.CSV.zip")
    with pytest.raises(ProviderError):
        Client(opener=FakeOpener({DAY_URL: [response]}), attempts=1, sleeper=lambda s: None).fetch(DAY_URL)


def test_manifests_are_parsed():
    manifest = (b"150383 297a16b493de7cf6ca809a7cc31d0b93 http://data.gdeltproject.org/gdeltv2/20261016121500.export.CSV.zip\n"
                b"318084 bb27f78ba45f69a17ea6ed7755e9f8ff http://data.gdeltproject.org/gdeltv2/20261016121500.mentions.CSV.zip\n")
    md5s = (b"9f1a5ad40ad2f2a4d2a2f0a1c2b3d4e5  20250101.export.CSV.zip\n"
            b"garbage line\n0123456789abcdef0123456789abcdef  20250102.export.CSV.zip\n")
    last, sums = "https://data.gdeltproject.org/gdeltv2/lastupdate.txt", "https://data.gdeltproject.org/events/md5sums"
    opener = FakeOpener({last: [FakeResponse(last, manifest)], sums: [FakeResponse(sums, md5s)]})
    client = Client(opener=opener, sleeper=lambda s: None)
    assert client.latest_slot() == datetime(2026, 10, 16, 12, 15, tzinfo=timezone.utc)
    assert client.daily_md5s() == {"20250101": "9f1a5ad40ad2f2a4d2a2f0a1c2b3d4e5",
                                   "20250102": "0123456789abcdef0123456789abcdef"}


def test_unpack_accepts_one_official_member_only():
    assert gdelt.unpack(archive("20250101.export.CSV", b"x\ty\n")) == b"x\ty\n"
    assert gdelt.unpack(archive("20250101121500.export.CSV", b"x\n")) == b"x\n"
    with pytest.raises(ProviderError, match="member name"):
        gdelt.unpack(archive("../evil.CSV", b"x"))
    two = io.BytesIO()
    with zipfile.ZipFile(two, "w") as zf:
        zf.writestr("20250101.export.CSV", b"a")
        zf.writestr("20250102.export.CSV", b"b")
    with pytest.raises(ProviderError, match="exactly one"):
        gdelt.unpack(two.getvalue())
    with pytest.raises(ProviderError, match="invalid"):
        gdelt.unpack(b"PK\x03\x04 not a zip")


def test_unpack_refuses_compression_bombs():
    bomb = archive("20250101.export.CSV", b"\0" * (5 * 1024 * 1024))  # compresses about 1000:1
    with pytest.raises(ProviderError, match="expansion"):
        gdelt.unpack(bomb)


def test_rows_flags_wrong_width_without_failing():
    good = "\t".join(["x"] * gdelt.DAILY.columns)
    out = list(gdelt.rows(f"{good}\nshort\trow\n{good}\r\n".encode(), gdelt.DAILY))
    assert [r is None for r in out] == [False, True, False]
