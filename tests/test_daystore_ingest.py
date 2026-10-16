from datetime import date, datetime, timezone

from synthetic import DAILY, FIFTEEN, archive, gdelt_row, tsv
from worldline import ingest
from worldline.daystore import DayStore, merge_stores
from worldline.gdelt import NotPublished, daily_url, day_slots, slot_url


def record(day, *, complete=True, kind="gdelt-daily", slots=96, fresh=100):
    return {"date": day, "complete": complete, "fresh": fresh, "provenance": {"kind": kind, "slots": slots}}


def test_round_trip_and_deterministic_bytes(tmp_path):
    store = DayStore(tmp_path)
    store.upsert([record("2025-01-02"), record("2025-01-01"), record("2025-02-01")])
    assert list(store.load()) == ["2025-01-01", "2025-01-02", "2025-02-01"]
    assert store.months() == ["2025-01", "2025-02"]
    assert list(store.load(start="2025-01-02", end="2025-01-31")) == ["2025-01-02"]
    first = store.path("days", "2025-01").read_bytes()
    other = DayStore(tmp_path / "again")
    other.upsert([record("2025-01-01"), record("2025-01-02")])
    assert other.path("days", "2025-01").read_bytes() == first  # gzip mtime 0, sorted keys
    assert store.upsert([record("2025-01-01")]) == 0  # unchanged record: no rewrite


def test_preferred_records_win(tmp_path):
    store = DayStore(tmp_path)
    store.upsert([record("2025-01-01", kind="gdelt-15min", slots=96)])
    store.upsert([record("2025-01-01", complete=False, kind="gdelt-15min", slots=40, fresh=1)])
    assert store.load()["2025-01-01"]["fresh"] == 100  # a partial never replaces a complete day
    store.upsert([record("2025-01-01", fresh=101)])
    assert store.load()["2025-01-01"]["provenance"]["kind"] == "gdelt-daily"
    store.upsert([record("2025-01-01", complete=False, kind="gdelt-15min", slots=10, fresh=5)], force=True)
    assert store.load()["2025-01-01"]["fresh"] == 5


def test_merge_prefers_better_record_across_stores(tmp_path):
    seed, state = DayStore(tmp_path / "seed"), DayStore(tmp_path / "state")
    seed.upsert([record("2025-01-01"), record("2025-01-02", complete=False, kind="gdelt-15min", slots=50)])
    state.upsert([record("2025-01-02", kind="gdelt-15min"), record("2025-01-03", complete=False, kind="gdelt-15min", slots=8)])
    merged = merge_stores(seed, state)
    assert list(merged) == ["2025-01-01", "2025-01-02", "2025-01-03"]
    assert merged["2025-01-02"]["complete"] is True


def test_usable():
    assert ingest.usable(record("2025-01-01"))
    assert ingest.usable(record("2025-01-01", complete=False, kind="gdelt-15min", slots=93))
    assert not ingest.usable(record("2025-01-01", complete=False, kind="gdelt-15min", slots=91))
    assert not ingest.usable({**record("2025-01-01"), "gap": True})
    assert not ingest.usable(None)


class ScriptedClient:
    """Serves archives from a dict; unknown URLs are 'not published'."""

    def __init__(self, files: dict[str, bytes]):
        self.files = files

    def fetch_with_meta(self, url):
        if url not in self.files:
            raise NotPublished(url)
        return self.files[url], {"served_md5": None, "transfer_verified": False}

    def fetch(self, url):
        return self.fetch_with_meta(url)[0]


def day_rows(layout, day: date, n: int = 5):
    key = f"{day:%Y%m%d}"
    return [gdelt_row(layout, event_id=f"{key}{i}", sqldate=key, added=key, root="01" if i % 2 else "19", quad="1" if i % 2 else "4",
                      country="NI", url=f"https://n{i}.example/a") for i in range(n)]


def test_acquire_prefers_daily_file_and_checks_listed_md5():
    day = date(2025, 5, 1)
    payload = archive(f"{day:%Y%m%d}.export.CSV", tsv(day_rows(DAILY, day)))
    client = ScriptedClient({daily_url(day): payload})
    from hashlib import md5
    rec, cooc, evidence = ingest.acquire_day(client, day, md5s={"20250501": md5(payload).hexdigest()})
    assert rec["complete"] and rec["fresh"] == 5
    assert rec["provenance"]["kind"] == "gdelt-daily" and rec["provenance"]["listed_md5_match"] is True
    rec, _, _ = ingest.acquire_day(client, day, md5s={"20250501": "0" * 32})
    assert rec["provenance"]["listed_md5_match"] is False  # recorded, not hidden


def test_acquire_falls_back_to_fifteen_minute_slots():
    day = date(2025, 5, 2)
    stamps = day_slots(day)
    files = {}
    for i, stamp in enumerate(stamps[:94]):  # two slots never published
        rows = day_rows(FIFTEEN, day, n=1)
        rows[0][0] = str(1000 + i)
        files[slot_url(stamp)] = archive(f"{stamp:%Y%m%d%H%M%S}.export.CSV", tsv(rows))
    rec, _, _ = ingest.acquire_day(ScriptedClient(files), day, latest=stamps[-1])
    assert rec["provenance"]["kind"] == "gdelt-15min"
    assert rec["provenance"]["slots"] == 94 and not rec["complete"] and rec["fresh"] == 94
    assert rec["provenance"]["missing_slots"] == ["2330", "2345"]
    assert ingest.usable(rec)  # 94 of 96 slots is enough to model


def test_unpublished_day_is_an_explicit_gap():
    day = date(2025, 5, 3)
    rec, _, _ = ingest.acquire_day(ScriptedClient({}), day, latest=datetime(2025, 5, 4, tzinfo=timezone.utc))
    assert rec["gap"] is True and rec["provenance"]["kind"] == "unavailable" and not ingest.usable(rec)


def test_slots_after_latest_are_not_requested():
    day = date(2025, 5, 4)
    requested = []

    class Recorder(ScriptedClient):
        def fetch(self, url):
            requested.append(url)
            return super().fetch(url)

    latest = datetime(2025, 5, 4, 1, 0, tzinfo=timezone.utc)
    ingest.acquire_day(Recorder({}), day, latest=latest)
    assert len(requested) == 5  # 00:00 .. 01:00
    assert all(url <= slot_url(latest) for url in requested)
