from datetime import date

from synthetic import DAILY, FIFTEEN, gdelt_row
from worldline.aggregate import DayAggregator
from worldline.daystore import REVISED_FIELDS

DAY = date(2025, 3, 10)


def sample_rows(layout):
    r = lambda **kw: gdelt_row(layout, **kw)  # noqa: E731
    rows = [
        r(event_id="1", sqldate="20250310", added="20250310", root="01", country="US", actor1="USA", actor2="CHN", url="https://www.a.com/x"),
        r(event_id="2", sqldate="20250309", added="20250310", root="19", base="190", quad="4", country="UP", actor1="RUS", actor2="UKR",
          url="https://www.a.com/x", lat="48.5", lon="37.9"),
        r(event_id="3", sqldate="20250310", added="20250310", root="19", base="193", quad="4", country="UP", actor1="RUS", actor2="UKR",
          url="https://b.org/y", lat="48.4", lon="38.1"),
        r(event_id="3", sqldate="20250310", added="20250310", root="19", base="193", quad="4", country="UP"),          # duplicate ID
        r(event_id="4", sqldate="20250210", added="20250310", root="04", quad="1", country="FR"),                    # stale anniversary
        r(event_id="5", sqldate="20250311", added="20250311", root="04", quad="1", country="FR"),                    # another day's file
        r(event_id="6", sqldate="20250310", added="20250310", root="99", quad="1", country="FR"),                    # invalid root
        r(event_id="7", sqldate="20250310", added="20250310", root="05", base="051", quad="1", country="", url="https://c.net/z"),
    ]
    return rows + [None]  # one malformed row


def aggregate(layout, window=False):
    aggregator = DayAggregator(DAY, window=window)
    aggregator.add_rows(iter(sample_rows(layout)), layout)
    return aggregator


def test_accounting_is_explicit():
    record, _ = aggregate(DAILY).finish()
    assert record["rows"] == 9 and record["malformed"] == 1 and record["duplicates"] == 1
    assert record["stale"] == 1 and record["offday"] == 1 and record["invalid"] == 1
    assert record["fresh"] == 4 and record["nogeo"] == 1
    assert sum(record["root"]) == record["fresh"]
    assert record["base"] == {"010": 1, "051": 1, "190": 1, "193": 1}


def test_country_statistics_and_dyads():
    record, _ = aggregate(DAILY).finish()
    ukraine = record["geo"]["UP"]
    assert ukraine["n"] == 2 and ukraine["root"][18] == 2
    assert ukraine["urls"] == 2 and ukraine["outlets"] == 2  # a.com and b.org
    assert record["dyad"] == {"RUS>UKR": [0, 0, 0, 2]}  # USA>CHN has one event, below the minimum of two
    assert record["urls"] == 3 and record["domains"] == {"a.com": 1, "b.org": 1, "c.net": 1}
    assert [48, 38, 2, 2] in record["spots"]


def test_same_article_cooccurrence():
    _, cooc = aggregate(DAILY).finish()
    # a.com/x carries codes 010 and 190 once; pairs seen in fewer than two articles are dropped.
    assert cooc["urls"] == 3 and cooc["pairs"] == {}
    aggregator = DayAggregator(DAY)
    rows = [gdelt_row(DAILY, event_id=str(i), sqldate="20250310", added="20250310", root=root, url=f"https://x.com/{i // 2}")
            for i, root in enumerate(["01", "04", "01", "04", "01", "19"])]
    aggregator.add_rows(iter(rows), DAILY)
    _, cooc = aggregator.finish()
    assert cooc["pairs"] == {"010|040": 2}


def test_daily_and_fifteen_minute_encodings_agree():
    daily, daily_cooc = aggregate(DAILY).finish()
    fifteen, fifteen_cooc = aggregate(FIFTEEN).finish()
    for key in daily:
        if key not in REVISED_FIELDS:
            assert daily[key] == fifteen[key], key
    assert daily_cooc == fifteen_cooc


def test_window_mode_accepts_rows_from_consecutive_days():
    aggregator = aggregate(FIFTEEN, window=True)
    record, _ = aggregator.finish()
    assert record["offday"] == 0
    assert record["fresh"] == 5  # event 5 is fresh relative to its own DATEADDED day


def test_evidence_lists_top_articles_for_busy_locations():
    aggregator = DayAggregator(DAY)
    rows = [gdelt_row(DAILY, event_id=str(i), sqldate="20250310", added="20250310", root="19", quad="4", country="SU",
                      url=f"https://news{i % 4}.example/story") for i in range(60)]
    aggregator.add_rows(iter(rows), DAILY)
    evidence = aggregator.evidence()
    entries = evidence["top"]["SU"]
    assert len(entries) == 3 and all(count == 15 for _, count in entries)
    assert all(evidence["urls"][index].startswith("https://news") for index, _ in entries)
