import json
from pathlib import Path

import pytest

from worldline.labels import build_labels, categories, clean_wikitext, countries_in, parse_year_article

ROOT = Path(__file__).resolve().parents[1]

ARTICLE = """
Intro text.
== Events ==
=== January ===
* [[January 3]] – A [[2025 Sudan airstrike|military airstrike]] kills 20 people in [[El Fasher]], [[Sudan]].<ref>{{cite web|url=https://x.example|title=x}}</ref>
* [[January 5]]
** [[Niger]]'s junta announces its withdrawal from the [[Economic Community of West African States|ECOWAS]].
** A 6.8 {{convert|6.8|M}} earthquake strikes [[New Mexico]], damaging buildings.
* [[January 14]] – [[February 2]] – Protests take place across [[South Sudan]] after the election.
* [[January 20]] – [[Donald Trump]] is inaugurated as the 47th [[President of the United States]].<ref name="a"/>
* An undated bullet that should not be assigned to the previous date.
* [[January 31]] – [[File:Map.png|thumb|A map of [[Ukraine]]]] Talks between Russia and Ukraine resume in [[Istanbul]].
=== February ===
* February 2 – Short.
== Deaths ==
* [[January 4]] – Someone notable, actor (b. 1950)
"""


@pytest.fixture(scope="module")
def events():
    return parse_year_article(ARTICLE, 2025)


def test_dated_entries_and_sub_bullets(events):
    assert [e["date"] for e in events] == ["2025-01-03", "2025-01-05", "2025-01-05", "2025-01-14", "2025-01-20", "2025-01-31"]
    assert all(e["source"] == "https://en.wikipedia.org/wiki/2025" for e in events)
    assert len({e["id"] for e in events}) == len(events)


def test_wikitext_is_cleaned(events):
    first = events[0]["text"]
    assert first == "A military airstrike kills 20 people in El Fasher, Sudan."
    assert "<ref" not in " ".join(e["text"] for e in events)
    assert events[3]["text"].startswith("Protests take place")  # date range anchored at its start date
    assert "File:" not in events[5]["text"] and "thumb" not in events[5]["text"]


def test_countries_resolve_longest_match_first(events):
    assert events[0]["countries"] == ["SDN"]
    assert events[1]["countries"] == ["NER"]  # Niger, not Nigeria
    assert events[2]["countries"] == ["USA"]  # New Mexico, not Mexico
    assert events[3]["countries"] == ["SSD"]  # South Sudan, not Sudan
    assert "USA" in events[4]["countries"]
    assert set(events[5]["countries"]) == {"RUS", "UKR", "TUR"}


def test_countries_in_handles_aliases_and_non_references():
    assert countries_in("Clashes in Gaza and the West Bank") == ["PSE"]
    assert countries_in("Latin American leaders meet") == []
    assert countries_in("The Democratic Republic of the Congo and Rwanda sign a deal") == ["COD", "RWA"]
    assert countries_in("Houthis attack a ship") == ["YEM"]


def test_categories():
    assert categories("A missile strike kills 12") == ["conflict"]
    assert categories("Parliament elects a new prime minister") == ["political"]
    assert categories("A magnitude 7 earthquake strikes") == ["disaster"]
    assert categories("A landslide victory in the election") == ["political"]  # not a disaster
    assert categories("A new museum opens") == ["other"]


def test_clean_wikitext_returns_link_targets():
    text, links = clean_wikitext("[[Kyiv|The capital]] is hit by [[drone]]s. [https://x.example Source]")
    assert text == "The capital is hit by drones. Source"
    assert links == ["Kyiv", "drone"]


def test_frozen_label_file_matches_its_sources():
    """The committed labels are exactly what the parser produces from the committed Wikipedia snapshots."""
    frozen = json.loads((ROOT / "data/labels/wikipedia_year_events.json").read_text(encoding="utf-8"))
    rebuilt = build_labels(ROOT / "data/labels/raw")
    assert frozen["version"] == rebuilt["version"]
    assert frozen["manifest"] == rebuilt["manifest"]
    assert frozen["events"] == rebuilt["events"]
    assert len(frozen["events"]) > 500
