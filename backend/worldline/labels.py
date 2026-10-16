"""Independent validation labels from Wikipedia's year articles ("2023", "2024", ...).

Why these labels
* They are written by Wikipedia editors under a notability guideline for
  international significance, independently of WORLDLINE, before we look at scores.
* Each entry has a date and links, so it can be tied to countries.

What they are not
* Not a census of events: coverage favours English-language and Western salience.
* The year article is edited after the fact; we freeze the exact wikitext used
  (SHA-256 in data/labels/manifest.json). Text is CC BY-SA 4.0, attributed.

Category rules below are declared before evaluation (protocol v2.0) and are
deliberately coarse keyword rules; an entry may belong to several categories.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import date
from functools import lru_cache
from pathlib import Path

from .reference import places

MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
          "October", "November", "December"]
LABEL_VERSION = "wikipedia-year-labels-2.0"

# ----------------------------------------------------------------------------- categories (pre-registered)
CATEGORY_RULES = {
    "conflict": r"\b(kill(?:s|ed|ing)?|dead|deaths?|attacks?|attacked|bomb(?:s|ed|ing|ings)?|air ?strikes?|strikes? on|missiles?|"
                r"drones?|shell(?:s|ed|ing)|invad(?:e|es|ed|ing)|invasion|wars?|clash(?:es|ed)?|fighting|offensive|massacre|"
                r"assassinat\w*|hostages?|terror\w*|gunm[ae]n|shootings?|militants?|insurgen\w*|rebels?|troops|military|"
                r"army|armed forces|coup|ceasefire|cease-fire|truce|armistice|explosions?)\b",
    "political": r"\b(elect(?:ion|ions|ed)|re-elected|referendum|president|presidential|prime minister|parliament\w*|"
                 r"impeach\w*|resign\w*|sworn|inaugurat\w*|government|cabinet|protests?|protesters|protested|"
                 r"demonstrat\w*|riots?|sanction\w*|treaty|agreement|accord|summit|talks|peace|diplomat\w*|tariffs?|"
                 r"martial law|arrest(?:s|ed)?|sentenced|convicted|indicted|constitution\w*|independence|annex\w*|"
                 r"recogni[sz]\w*|ministers?|chancellor|king|queen|monarch|regime|junta|opposition)\b",
    "disaster": r"\b(earthquakes?|floods?|flooding|wildfires?|fires?|hurricanes?|cyclones?|typhoons?|storms?|tsunamis?|"
                r"volcan\w*|eruptions?|landslides?(?!\s+(?:victory|majority|win|wins|won|election|defeat))|mudslides?|crash(?:es|ed)?|collisions?|derail\w*|heat ?waves?|"
                r"droughts?|outbreaks?|epidemic|pandemic|famine|avalanches?|tornado(?:es)?|sank|sinks|capsiz\w*|stampede)\b",
}
CATEGORY_PATTERNS = {k: re.compile(v, re.IGNORECASE) for k, v in CATEGORY_RULES.items()}


def categories(text: str) -> list[str]:
    found = [name for name, pattern in CATEGORY_PATTERNS.items() if pattern.search(text)]
    return found or ["other"]


# ----------------------------------------------------------------------------- gazetteer
# Demonyms and frequent aliases. Longest-match-first with span masking resolves
# "South Sudan" vs "Sudan", "Niger" vs "Nigeria", "New Mexico" vs "Mexico".
ALIASES: dict[str, list[str]] = {
    "AFG": ["Afghan", "Afghans", "Taliban", "Kabul"], "ALB": ["Albanian"], "DZA": ["Algerian"], "AGO": ["Angolan"],
    "ARG": ["Argentine", "Argentinian", "Buenos Aires"], "ARM": ["Armenian", "Armenians", "Yerevan"],
    "AUS": ["Australian", "Australians", "New South Wales", "Queensland", "Victoria, Australia", "Sydney", "Melbourne"],
    "AUT": ["Austrian", "Vienna"], "AZE": ["Azerbaijani", "Azerbaijanis", "Baku", "Nagorno-Karabakh"],
    "BHR": ["Bahraini"], "BGD": ["Bangladeshi", "Dhaka"], "BLR": ["Belarusian", "Minsk"], "BEL": ["Belgian", "Brussels"],
    "BEN": ["Beninese"], "BTN": ["Bhutanese"], "BOL": ["Bolivian"], "BIH": ["Bosnian", "Bosnia", "Sarajevo"],
    "BWA": ["Botswanan", "Motswana"], "BRA": ["Brazilian", "Brazilians", "Brasília", "Rio de Janeiro", "São Paulo"],
    "BRN": ["Bruneian"], "BGR": ["Bulgarian"], "BFA": ["Burkinabé", "Burkinabe", "Ouagadougou"], "BDI": ["Burundian"],
    "KHM": ["Cambodian", "Phnom Penh"], "CMR": ["Cameroonian"], "CAN": ["Canadian", "Canadians", "Ottawa", "Ontario", "Quebec", "British Columbia", "Alberta", "Toronto"],
    "CAF": ["Central African Republic"], "TCD": ["Chadian", "N'Djamena"], "CHL": ["Chilean", "Santiago, Chile"],
    "CHN": ["Chinese", "Beijing", "Shanghai", "Xinjiang", "Tibet", "Tibetan"], "COL": ["Colombian", "Bogotá"],
    "COD": ["Democratic Republic of the Congo", "DR Congo", "DRC", "Congolese", "Kinshasa", "Goma", "M23"],
    "COG": ["Republic of the Congo", "Congo-Brazzaville", "Brazzaville"], "CRI": ["Costa Rican"],
    "HRV": ["Croatian", "Zagreb"], "CUB": ["Cuban", "Havana"], "CYP": ["Cypriot"], "CZE": ["Czech", "Czech Republic", "Prague"],
    "DNK": ["Danish", "Copenhagen", "Greenland"], "DJI": ["Djiboutian"], "DOM": ["Dominican Republic"],
    "ECU": ["Ecuadorian", "Quito"], "EGY": ["Egyptian", "Egyptians", "Cairo", "Sinai"], "SLV": ["Salvadoran"],
    "ERI": ["Eritrean"], "EST": ["Estonian", "Tallinn"], "SWZ": ["Swazi", "Swaziland"], "ETH": ["Ethiopian", "Addis Ababa", "Tigray", "Amhara"],
    "FJI": ["Fijian"], "FIN": ["Finnish", "Helsinki"], "FRA": ["French", "Paris", "Marseille", "New Caledonia"],
    "GAB": ["Gabonese"], "GMB": ["Gambian"], "GEO": ["Georgian", "Tbilisi"], "DEU": ["German", "Germans", "Berlin", "Munich"],
    "GHA": ["Ghanaian", "Accra"], "GRC": ["Greek", "Athens"], "GTM": ["Guatemalan"], "GIN": ["Guinean", "Conakry"],
    "GNB": ["Guinea-Bissau"], "HTI": ["Haitian", "Port-au-Prince"], "HND": ["Honduran"], "HKG": ["Hong Kong"],
    "HUN": ["Hungarian", "Budapest"], "ISL": ["Icelandic"], "IND": ["Indian government", "Indian Army", "New Delhi", "Delhi", "Mumbai", "Manipur", "Kashmir"],
    "IDN": ["Indonesian", "Jakarta", "Java", "Sumatra", "Papua"], "IRN": ["Iranian", "Iranians", "Tehran"],
    "IRQ": ["Iraqi", "Baghdad", "Kurdistan Region"], "IRL": ["Irish", "Republic of Ireland", "Dublin"],
    "ISR": ["Israeli", "Israelis", "Jerusalem", "Tel Aviv", "Netanyahu", "Israel Defense Forces", "IDF"],
    "ITA": ["Italian", "Rome", "Milan", "Sicily"], "CIV": ["Ivorian", "Côte d'Ivoire", "Ivory Coast", "Abidjan"],
    "JAM": ["Jamaican"], "JPN": ["Japanese", "Tokyo", "Osaka", "Okinawa"], "JOR": ["Jordanian", "Amman"],
    "KAZ": ["Kazakh", "Kazakhstani", "Astana"], "KEN": ["Kenyan", "Nairobi"], "XKX": ["Kosovar", "Kosovo", "Pristina"],
    "KWT": ["Kuwaiti"], "KGZ": ["Kyrgyz", "Bishkek"], "LAO": ["Lao", "Laotian", "Laos"], "LVA": ["Latvian", "Riga"],
    "LBN": ["Lebanese", "Beirut", "Hezbollah"], "LBR": ["Liberian"], "LBY": ["Libyan", "Tripoli", "Benghazi"],
    "LTU": ["Lithuanian", "Vilnius"], "MDG": ["Malagasy"], "MWI": ["Malawian"], "MYS": ["Malaysian", "Kuala Lumpur"],
    "MDV": ["Maldivian"], "MLI": ["Malian", "Bamako"], "MLT": ["Maltese"], "MRT": ["Mauritanian"], "MUS": ["Mauritian"],
    "MEX": ["Mexican", "Mexico City", "Sinaloa"], "MDA": ["Moldovan", "Chișinău", "Transnistria"], "MNG": ["Mongolian"],
    "MNE": ["Montenegrin"], "MAR": ["Moroccan", "Rabat"], "MOZ": ["Mozambican", "Maputo", "Cabo Delgado"],
    "MMR": ["Burmese", "Burma", "Myanmar", "Yangon", "Naypyidaw", "Rohingya"], "NAM": ["Namibian"],
    "NPL": ["Nepali", "Nepalese", "Kathmandu"], "NLD": ["Dutch", "Netherlands", "Amsterdam", "The Hague"],
    "NZL": ["New Zealand", "New Zealander", "Wellington", "Auckland"], "NIC": ["Nicaraguan"], "NER": ["Nigerien", "Niamey"],
    "NGA": ["Nigerian", "Nigerians", "Abuja", "Lagos", "Boko Haram"], "PRK": ["North Korea", "North Korean", "DPRK", "Pyongyang", "Kim Jong Un"],
    "MKD": ["North Macedonian", "Macedonian", "Skopje"], "NOR": ["Norwegian", "Oslo"], "OMN": ["Omani"],
    "PAK": ["Pakistani", "Islamabad", "Karachi", "Lahore", "Balochistan", "Khyber Pakhtunkhwa"],
    "PSE": ["Palestinian", "Palestinians", "Palestine", "Gaza", "Gaza Strip", "West Bank", "Hamas", "Rafah", "Khan Yunis", "Khan Younis"],
    "PAN": ["Panamanian", "Panama Canal"], "PNG": ["Papua New Guinea", "Papua New Guinean"], "PRY": ["Paraguayan"],
    "PER": ["Peruvian", "Lima"], "PHL": ["Filipino", "Philippine", "Philippines", "Manila", "Mindanao"],
    "POL": ["Polish", "Poles", "Warsaw"], "PRT": ["Portuguese", "Lisbon"], "QAT": ["Qatari", "Doha"],
    "ROU": ["Romanian", "Bucharest"], "RUS": ["Russian", "Russians", "Moscow", "Kremlin", "Putin", "Kursk", "Belgorod", "Chechnya", "Dagestan", "Wagner Group"],
    "RWA": ["Rwandan", "Kigali"], "SAU": ["Saudi", "Saudi Arabian", "Riyadh", "Jeddah", "Mecca"],
    "SEN": ["Senegalese", "Dakar"], "SRB": ["Serbian", "Belgrade"], "SLE": ["Sierra Leonean", "Freetown"],
    "SGP": ["Singaporean"], "SVK": ["Slovak", "Bratislava"], "SVN": ["Slovenian", "Slovene"], "SOM": ["Somali", "Somalia", "Mogadishu", "al-Shabaab", "Al-Shabaab", "Somaliland"],
    "ZAF": ["South African", "Pretoria", "Johannesburg", "Cape Town"], "KOR": ["South Korea", "South Korean", "Seoul"],
    "SSD": ["South Sudan", "South Sudanese", "Juba"], "ESP": ["Spanish", "Madrid", "Barcelona", "Catalonia", "Valencia"],
    "LKA": ["Sri Lankan", "Colombo"], "SDN": ["Sudanese", "Khartoum", "Darfur", "El Fasher", "Rapid Support Forces"],
    "SUR": ["Surinamese"], "SWE": ["Swedish", "Stockholm"], "CHE": ["Swiss", "Geneva", "Zurich", "Bern"],
    "SYR": ["Syrian", "Syrians", "Damascus", "Aleppo", "Idlib", "Assad"], "TWN": ["Taiwanese", "Taipei"],
    "TJK": ["Tajik", "Tajikistani", "Dushanbe"], "TZA": ["Tanzanian", "Dar es Salaam", "Zanzibar"],
    "THA": ["Thai", "Bangkok"], "TLS": ["East Timor", "Timorese"], "TGO": ["Togolese", "Lomé"],
    "TUN": ["Tunisian", "Tunis"], "TUR": ["Turkish", "Türkiye", "Ankara", "Istanbul", "Erdoğan", "Erdogan"],
    "TKM": ["Turkmen"], "UGA": ["Ugandan", "Kampala"], "UKR": ["Ukrainian", "Ukrainians", "Kyiv", "Kiev", "Kharkiv", "Odesa", "Odessa", "Donetsk", "Luhansk", "Donbas", "Zaporizhzhia", "Kherson", "Crimea", "Zelenskyy", "Zelensky"],
    "ARE": ["Emirati", "UAE", "Abu Dhabi", "Dubai"], "GBR": ["British", "UK", "U.K.", "England", "English", "Scotland", "Scottish", "Wales", "Welsh", "Northern Ireland", "London", "Manchester"],
    "USA": ["U.S.", "US", "USA", "American", "Americans", "Washington, D.C.", "White House", "Pentagon", "New York City", "Los Angeles", "Chicago", "Trump", "Biden",
            "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado", "Connecticut", "Delaware", "Florida", "Hawaii", "Idaho",
            "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana", "Maine", "Maryland", "Massachusetts", "Michigan",
            "Minnesota", "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada", "New Hampshire", "New Jersey", "New Mexico",
            "New York", "North Carolina", "North Dakota", "Ohio", "Oklahoma", "Oregon", "Pennsylvania", "Rhode Island",
            "South Carolina", "South Dakota", "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "West Virginia", "Wisconsin", "Wyoming",
            "Puerto Rico", "New Orleans", "Washington state"],
    "URY": ["Uruguayan", "Montevideo"], "UZB": ["Uzbek", "Tashkent"], "VEN": ["Venezuelan", "Caracas", "Maduro"],
    "VNM": ["Vietnamese", "Hanoi", "Ho Chi Minh City"], "YEM": ["Yemeni", "Sanaa", "Aden", "Houthi", "Houthis"],
    "ZMB": ["Zambian", "Lusaka"], "ZWE": ["Zimbabwean", "Harare"], "VAT": ["Vatican", "Holy See", "Pope"],
}
# Phrases removed before matching because they contain a country word but do not refer to it.
NON_REFERENCES = ["Latin America", "Latin American", "South America", "South American", "North America",
                  "North American", "Central America", "Central American", "Native American", "American Samoa",
                  "Indian Ocean", "Arab League", "African Union", "Georgia (U.S. state)", "Atlanta, Georgia",
                  "Savannah, Georgia", "Jordan River", "Gulf of Mexico", "Gulf of America", "Guinea worm",
                  "English Channel", "New England", "Turkey Point", "Chad Daybell", "Michael Jordan"]
AMBIGUOUS_CAPITALS = {"Victoria", "Kingston", "Georgetown", "Hamilton", "San José", "Saint John's", "St. John's",
                      "Santiago", "Valletta", "Washington", "London", "Paris", "Moscow", "Rome", "Athens",
                      "Melekeok", "Avarua", "Alofi", "Yaren", "Funafuti", "Ngerulmud", "Road Town", "The Valley",
                      "Plymouth", "Jamestown", "Adamstown", "Stanley", "Kingstown", "Castries", "Basseterre",
                      "Roseau", "Saint George's", "Nassau", "Belmopan", "Tórshavn"}


def _fold(text: str) -> str:
    return unicodedata.normalize("NFKC", text)


@lru_cache(maxsize=1)
def gazetteer() -> list[tuple[re.Pattern, str]]:
    entries: dict[str, str] = {}
    for iso3, place in places().items():
        if place.population < 5000 and iso3 not in ("VAT",):
            continue
        entries[place.name] = iso3
        if place.capital and place.capital not in AMBIGUOUS_CAPITALS and len(place.capital) >= 4:
            entries.setdefault(place.capital, iso3)
    from .reference import REFERENCE_DIR  # GeoNames formal names
    for line in (REFERENCE_DIR / "geonames_countryInfo.txt").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            cols = line.split("\t")
            if cols[1] in places() and places()[cols[1]].population >= 5000:
                entries.setdefault(cols[4].strip(), cols[1])
    for iso3, names in ALIASES.items():
        for name in names:
            entries[name] = iso3
    for ambiguous in ("Georgia", "Jordan", "Chad", "Turkey", "Guinea", "Niger", "Dominica", "Congo", "Korea", "Ireland",
                      "Sudan", "India", "China", "Israel", "Iran", "Russia", "Ukraine", "United States", "United Kingdom"):
        pass  # kept via GeoNames names; overlaps are resolved by longest-match-first
    entries["Congo"] = "COD"
    entries["Korea"] = "KOR"
    entries["Georgia"] = "GEO"
    ordered = sorted(entries.items(), key=lambda kv: -len(kv[0]))
    patterns = []
    for name, iso3 in ordered:
        flags = 0 if name.isupper() or name in ("US", "UK", "IDF", "DRC", "UAE", "DPRK", "M23") else re.IGNORECASE
        patterns.append((re.compile(r"(?<![\w-])" + re.escape(_fold(name)) + r"(?![\w-])", flags), iso3))
    return patterns


def countries_in(text: str) -> list[str]:
    text = _fold(text)
    for phrase in NON_REFERENCES:
        text = re.sub(re.escape(phrase), " ", text, flags=re.IGNORECASE)
    found: list[str] = []
    masked = list(text)
    for pattern, iso3 in gazetteer():
        for match in pattern.finditer("".join(masked)):
            if iso3 not in found:
                found.append(iso3)
            for i in range(match.start(), match.end()):
                masked[i] = " "
    return found


# ----------------------------------------------------------------------------- wikitext parsing
def _strip_templates(text: str) -> str:
    def convert(match):
        parts = match.group(1).split("|")
        if parts[0].strip().lower() == "convert" and len(parts) >= 3:
            return f"{parts[1]} {parts[2]}"
        if parts[0].strip() == "M" and len(parts) >= 3:
            return f"M{parts[1]} {parts[2]}"
        if parts[0].strip().lower() in ("nowrap", "nobr") and len(parts) >= 2:
            return parts[1]
        return ""
    for _ in range(4):  # nested templates
        text = re.sub(r"\{\{([^{}]*)\}\}", convert, text)
    return text


def _remove_media(text: str) -> str:
    """Drop [[File:...]] / [[Image:...]] blocks, whose captions may contain nested links."""
    out, i = [], 0
    lowered = text.lower()
    while i < len(text):
        if lowered.startswith("[[file:", i) or lowered.startswith("[[image:", i):
            depth, j = 0, i
            while j < len(text) - 1:
                if text.startswith("[[", j):
                    depth += 1
                    j += 2
                elif text.startswith("]]", j):
                    depth -= 1
                    j += 2
                    if depth == 0:
                        break
                else:
                    j += 1
            i = j
            continue
        out.append(text[i])
        i += 1
    return "".join(out)


def clean_wikitext(raw: str) -> tuple[str, list[str]]:
    """Return (plain text, link targets)."""
    text = _remove_media(re.sub(r"<!--.*?-->", "", raw, flags=re.DOTALL))
    text = re.sub(r"<ref[^>/]*/>", "", text)
    text = re.sub(r"<ref[^>]*>.*?</ref>", "", text, flags=re.DOTALL)
    text = re.sub(r"<ref[^>]*>.*$", "", text, flags=re.DOTALL)  # reference continuing on later lines
    text = re.sub(r"<[^>]+>", "", text)
    text = _strip_templates(text)
    text = re.sub(r"\{\{.*$", "", text, flags=re.DOTALL)  # unclosed template continuing on later lines
    links: list[str] = []

    def link(match):
        target, _, label = match.group(1).partition("|")
        target = target.strip()
        if target.lower().startswith(("file:", "image:", "category:")):
            return ""
        links.append(target)
        return label.strip() or target

    text = re.sub(r"\[\[([^\[\]]*)\]\]", link, text)
    text = re.sub(r"\[https?://\S+\s*([^\]]*)\]", r"\1", text)
    text = text.replace("'''", "").replace("''", "").replace("&nbsp;", " ").replace("&ndash;", "–").replace("&mdash;", "—")
    text = re.sub(r"\s+", " ", text).strip(" *:-–—")
    return text, links


_DATE_LINK = re.compile(r"^\[\[(" + "|".join(MONTHS) + r") (\d{1,2})\]\]")
_DATE_PLAIN = re.compile(r"^(" + "|".join(MONTHS) + r") (\d{1,2})\b")


def parse_year_article(wikitext: str, year: int) -> list[dict]:
    """Extract dated entries from the 'Events' section of a Wikipedia year article."""
    match = re.search(r"^==\s*Events\s*==\s*$", wikitext, flags=re.MULTILINE)
    if not match:
        raise ValueError(f"no Events section in {year} article")
    end = re.search(r"^==[^=].*==\s*$", wikitext[match.end():], flags=re.MULTILINE)
    section = wikitext[match.end(): match.end() + (end.start() if end else len(wikitext))]
    events: list[dict] = []
    current: date | None = None
    for raw_line in section.splitlines():
        line = raw_line.strip()
        if not line.startswith("*"):
            continue
        depth = len(line) - len(line.lstrip("*"))
        body = line.lstrip("*").strip()
        for dash in ("{{ndash}}", "{{snd}}", "{{spaced ndash}}", "&ndash;", "{{mdash}}", "&mdash;"):
            body = body.replace(dash, " – ")
        found = _DATE_LINK.match(body) or _DATE_PLAIN.match(body)
        if depth == 1 and found:
            try:
                current = date(year, MONTHS.index(found.group(1)) + 1, int(found.group(2)))
            except ValueError:
                current = None
            body = body[found.end():]
            # Date ranges ("[[January 14]] – [[February 2]] – ...") are anchored at the start date.
            body = re.sub(r"^\s*[–—-]\s*\[\[(?:" + "|".join(MONTHS) + r") \d{1,2}(?:\|[^\]]*)?\]\]", "", body)
            body = re.sub(r"^\s*[–—-]\s*\d{1,2}(?!\d)", "", body)  # "[[June 1]]–29 – ..."
            body = re.sub(r"^\s*[–—-]\s*", "", body)
            if not body.strip():
                continue  # a date header with sub-bullets
        elif depth == 1:
            current = None  # undated top-level bullet: skip rather than guess a date
            continue
        if current is None or not body.strip():
            continue
        text, links = clean_wikitext(body)
        if len(text) < 12:
            continue
        searchable = text + " " + " ".join(links)
        identifier = hashlib.sha256(f"{current.isoformat()}|{text}".encode()).hexdigest()[:12]
        events.append({"id": f"wp{year}-{identifier}", "date": current.isoformat(), "text": text,
                       "links": links[:12], "countries": countries_in(searchable), "categories": categories(text),
                       "source": f"https://en.wikipedia.org/wiki/{year}"})
    return events


def build_labels(raw_dir: Path) -> dict:
    files = sorted(raw_dir.glob("wikipedia_*.wikitext"))
    events: list[dict] = []
    manifest = []
    for path in files:
        year = int(path.stem.split("_")[1])
        raw = path.read_text(encoding="utf-8")
        parsed = parse_year_article(raw, year)
        events.extend(parsed)
        manifest.append({"article": f"https://en.wikipedia.org/wiki/{year}", "file": path.name,
                         "sha256": hashlib.sha256(raw.encode()).hexdigest(), "events": len(parsed)})
    events.sort(key=lambda e: (e["date"], e["id"]))
    return {"version": LABEL_VERSION, "license": "CC BY-SA 4.0 — text from Wikipedia year articles; see sources",
            "attribution": "Wikipedia contributors", "category_rules": CATEGORY_RULES, "manifest": manifest,
            "events": events}


def save_labels(labels: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(labels, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
