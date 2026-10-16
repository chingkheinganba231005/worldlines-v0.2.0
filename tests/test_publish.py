"""End to end on synthetic data: day records -> analysis -> scenarios -> the static JSON API and RSS feed."""
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pytest

from worldline.geo import build_map
from worldline.pipeline import analyze
from worldline.publish import publish_all, return_period, rp_text
from worldline.scenarios import ScenarioConfig, build_scenarios

ROOT = Path(__file__).resolve().parents[1]
SPIKE = "2024-02-15"


@pytest.fixture(scope="module")
def site(synthetic_spike, tmp_path_factory):
    records, cooc = synthetic_spike
    analysis = analyze(records, cooc, semantic=False, log=lambda *a: None)
    clean = analysis.panel.usable & ~analysis.global_["instrument"]["degraded"]
    scenarios = build_scenarios(analysis.panel, clean, cfg=ScenarioConfig(countries=6, bootstrap=20), skill_split="2024-01-01")
    model = json.loads((ROOT / "data/model/published.json").read_text())
    labels = {"license": "CC BY-SA 4.0", "attribution": "test", "manifest": [],
              "events": [{"id": "wp-test-1", "date": SPIKE, "text": "Fighting intensifies in Sudan.", "countries": ["SDN"],
                          "categories": ["conflict"]}]}
    evidence = {SPIKE: {"schema": "worldline-evidence-v1", "date": SPIKE, "urls": ["https://www.news.example/sudan", "javascript:alert(1)"],
                        "top": {"SU": [[0, 40], [1, 30]]}}}
    validation = json.loads((ROOT / "research/results.json").read_text())
    out = tmp_path_factory.mktemp("site")
    nowcast = {"provisional": True, "countries": [], "through": "2024-03-06 12:00"}
    meta = publish_all(analysis, model, labels, evidence, records, scenarios, validation, build_map(), out, nowcast=nowcast,
                       base_url="https://example.github.io/worldline/", build={"mode": "test"})
    return out, meta


def load(out, name):
    return json.loads((out / "data" / name).read_text(encoding="utf-8"))


def test_every_file_is_written_and_strict_json(site):
    out, meta = site
    for name in ("latest.json", "timeline.json", "grid.json", "countries.json", "worldlines.json", "event_space.json",
                 "scenarios.json", "validation.json", "labels.json", "map.json", "meta.json"):
        text = (out / "data" / name).read_text(encoding="utf-8")
        assert "NaN" not in text and "Infinity" not in text, name
        json.loads(text)
    assert len(list((out / "data" / "country").glob("*.json"))) == meta["monitored"] == 24
    assert meta["data_as_of"] == "2024-03-05" and meta["detector"] == "worldline-v2.1"


def test_the_injected_event_is_published_with_its_explanation(site):
    out, _ = site
    sudan = load(out, "country/SDN.json")
    alarm = next(a for a in sudan["alarms"] if a["date"] == SPIKE)
    assert alarm["tier"] >= 2 and alarm["return_period"] >= 365
    channels = [d["channel"] for d in alarm["drivers"]]
    assert set(channels) == {"attention", "mix", "conflict"}
    assert any("Coercion and violence" in d["text"] for d in alarm["drivers"])
    assert alarm["evidence"] == [{"url": "https://www.news.example/sudan", "domain": "news.example", "events": 40}]  # unsafe URL dropped
    assert alarm["wikipedia"][0]["id"] == "wp-test-1"
    t = sudan["first_date"]
    assert t == "2023-01-01" and len(sudan["series"]["u"]) == 430


def test_quiet_countries_rarely_alarm(site):
    out, _ = site
    timeline = load(out, "timeline.json")
    spike = timeline["dates"].index(SPIKE)
    assert "SDN" in timeline["top"][spike]
    total = sum(timeline["alarms"]["unusual"]) + sum(timeline["alarms"]["rare"]) + sum(timeline["alarms"]["extreme"])
    # The outlet gate (>= 20 publishers) and the 1-in-100 threshold keep false alarms on quiet synthetic data rare.
    assert total <= 30


def test_latest_and_feed(site):
    out, _ = site
    latest = load(out, "latest.json")
    assert latest["date"] == "2024-03-05" and latest["nowcast"]["provisional"] is True
    assert latest["pulse"]["label"] in {"Calm", "Typical", "Busy", "Turbulent", "Exceptional"}
    assert len(latest["mix"]["today"]) == 7 and abs(sum(latest["mix"]["today"]) - 1) < 1e-3
    feed = ET.fromstring((out / "feed.xml").read_text(encoding="utf-8"))
    titles = [item.findtext("title") for item in feed.iter("item")]
    assert any("Sudan" in title and SPIKE in title for title in titles)
    assert all(item.findtext("link").startswith("https://example.github.io/worldline/#/country/") for item in feed.iter("item"))


def test_scenarios_and_embeddings_payloads(site):
    out, _ = site
    scenarios = load(out, "scenarios.json")
    n = len(scenarios["countries"])
    assert n == 6 and np.array(scenarios["median"]).shape == (n, scenarios["horizon"] + 1, n)
    assert np.all(np.array(scenarios["lo"]) <= np.array(scenarios["hi"]) + 1e-9)
    space = load(out, "event_space.json")
    assert len(space["codes"]) == 20 and space["checks"]["knn_quadclass_accuracy"] > space["checks"]["majority_baseline"]
    worldlines = load(out, "worldlines.json")
    assert set(worldlines["xy"]) == set(load(out, "countries.json")["countries"][i]["iso3"] for i in range(24))


def test_validation_carries_the_prospective_record(site):
    out, _ = site
    validation = load(out, "validation.json")
    assert validation["prospective"]["since"] == "2026-10-16"
    assert validation["prospective"]["alarms"] == 0  # synthetic data ends long before launch


def test_return_period_text():
    assert return_period(0.01) == pytest.approx(100) and rp_text(0.01) == "1-in-100 days"
    assert rp_text(1e-9) == "1-in-5,000+ days" and rp_text(None) == "—" and return_period(float("nan")) is None
