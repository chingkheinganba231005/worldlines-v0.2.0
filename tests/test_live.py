import math
from datetime import date, datetime, timedelta, timezone

import numpy as np

from synthetic import DAILY, FIFTEEN, archive, gdelt_row, tsv
from worldline import live
from worldline.daystore import DayStore
from worldline.gdelt import NotPublished, daily_url, slot_url

LATEST = datetime(2026, 10, 16, 0, 45, tzinfo=timezone.utc)


class ScriptedClient:
    def __init__(self, files: dict[str, bytes]):
        self.files = files
        self.requested: list[str] = []

    def latest_slot(self):
        return LATEST

    def daily_md5s(self):
        return {}

    def fetch_with_meta(self, url):
        self.requested.append(url)
        if url not in self.files:
            raise NotPublished(url)
        return self.files[url], {"served_md5": None, "transfer_verified": False}

    def fetch(self, url):
        return self.fetch_with_meta(url)[0]


def slot_file(stamp: datetime, country: str, n: int) -> bytes:
    key = f"{stamp:%Y%m%d}"
    rows = [gdelt_row(FIFTEEN, event_id=f"{stamp:%d%H%M}{i:03d}", sqldate=key, added=key, root="19", quad="4", country=country,
                      url=f"https://site{i % 7}.example/{stamp:%H%M}/{i}") for i in range(n)]
    return archive(f"{stamp:%Y%m%d%H%M%S}.export.CSV", tsv(rows))


def test_refresh_keeps_recent_days_current_and_never_refetches_final_ones(tmp_path):
    window = [LATEST - timedelta(minutes=15 * k) for k in range(96)]
    files = {slot_url(s): slot_file(s, "SU", 3) for s in window}
    yesterday = date(2026, 10, 15)
    key = f"{yesterday:%Y%m%d}"
    files[daily_url(yesterday)] = archive(f"{key}.export.CSV", tsv(
        [gdelt_row(DAILY, event_id=f"9{i}", sqldate=key, added=key, country="SU") for i in range(4)]))
    known = {
        "2026-10-10": {"complete": False, "provenance": {"kind": "gdelt-15min", "slots": 60}},   # old partial: final
        "2026-10-11": {"complete": True, "provenance": {"kind": "gdelt-daily", "slots": 96}},   # final
        "2026-10-15": {"complete": True, "provenance": {"kind": "gdelt-15min", "slots": 96}},   # young: upgrade to daily file
    }
    client = ScriptedClient(files)
    state = DayStore(tmp_path)
    result = live.refresh(state, known, client, start="2026-10-10", log=lambda *a: None)
    acquired = {a["date"]: a for a in result["summary"]["acquired"]}
    assert set(acquired) == {"2026-10-12", "2026-10-13", "2026-10-14", "2026-10-15"}
    assert acquired["2026-10-15"]["kind"] == "gdelt-daily"
    assert daily_url(date(2026, 10, 10)) not in client.requested and daily_url(date(2026, 10, 11)) not in client.requested
    days = state.load()
    today = days["2026-10-16"]
    assert today["provenance"]["slots"] == 4 and today["complete"] is False and today["fresh"] == 12
    assert days["2026-10-12"].get("gap") is True  # nothing published: an explicit gap, not a quiet day
    assert result["summary"]["window_slots"] == 96
    record, _ = result["window"].finish()
    assert record["fresh"] == 96 * 3 and record["geo"]["SU"]["urls"] == 96 * 3


def test_nowcast_scores_the_rolling_window_against_each_countrys_forecast():
    from worldline.aggregate import DayAggregator
    aggregator = DayAggregator(date(2026, 10, 16), window=True)
    rows = [gdelt_row(FIFTEEN, event_id=str(i), sqldate="20261016", added="20261016", country="SU" if i < 40 else "US",
                      url=f"https://x{i}.example/a") for i in range(400)]
    aggregator.add_rows(iter(rows), FIFTEEN)
    rng = np.random.default_rng(0)
    calib = sorted(float(v) for v in rng.normal(0, 0.2, 365))
    inputs = {"target_date": "2026-10-16", "countries": {
        "SDN": {"pred": math.log(0.02), "calib": calib},   # expected 2% of articles, observed 10%
        "USA": {"pred": math.log(0.90), "calib": calib}}}
    out = live.nowcast(aggregator, inputs, {"window_to": "2026-10-16 01:00", "window_from": "2026-10-15 01:00", "window_slots": 96})
    assert out["provisional"] is True and out["articles"] == 400
    assert [c["iso3"] for c in out["countries"]] == ["SDN"]
    sudan = out["countries"][0]
    assert sudan["ratio"] > 4 and sudan["p"] < 0.001 and sudan["name"] == "Sudan" and sudan["flag"] == "🇸🇩"
    assert live.nowcast(aggregator, None, {}) is None


def test_prospective_scores_only_alarms_after_launch():
    labels = [{"date": "2026-10-20", "countries": ["SDN"]}, {"date": "2026-11-01", "countries": ["FRA"]}]
    alarms = [{"date": "2026-10-01", "iso3": "SDN"},   # before launch: not part of the prospective record
              {"date": "2026-10-19", "iso3": "SDN"},   # one day before the label: hit
              {"date": "2026-10-22", "iso3": "SDN"},   # two days after: hit
              {"date": "2026-10-23", "iso3": "SDN"},   # three days after: miss
              {"date": "2026-11-01", "iso3": "DEU"}]   # other country: miss
    record = live.prospective(alarms, labels)
    assert record["since"] == live.LAUNCH_DATE and record["alarms"] == 4 and record["matched"] == 2
    assert [a["matched"] for a in record["items"]] == [True, True, False, False]
