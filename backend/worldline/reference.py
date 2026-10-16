"""Reference vocabularies: places (countries/territories) and the CAMEO event codebook.

Places are keyed by ISO 3166-1 alpha-3. GDELT locates events with FIPS 10-4
country codes (ActionGeo_CountryCode) and labels actors with CAMEO country
codes (mostly ISO alpha-3, plus regional pseudo-codes). Both are mapped here so
that every downstream statistic, map shape and validation label speaks ISO3.

Sources (bundled in data/reference/, see docs/data_sources_and_rights.md):
- GeoNames countryInfo.txt (CC BY 4.0): ISO2/ISO3/ISO numeric/FIPS, names,
  continent, population, neighbours.
- GDELT lookups (CAMEO.eventcodes.txt, FIPS.country.txt, CAMEO.country.txt).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

REFERENCE_DIR = Path(__file__).resolve().parents[2] / "data" / "reference"

# --------------------------------------------------------------------------
# CAMEO event roots and plain-language families
# --------------------------------------------------------------------------
ROOTS = [f"{i:02d}" for i in range(1, 21)]
ROOT_LABELS = {
    "01": "Make public statement", "02": "Appeal", "03": "Express intent to cooperate",
    "04": "Consult", "05": "Engage in diplomatic cooperation", "06": "Engage in material cooperation",
    "07": "Provide aid", "08": "Yield", "09": "Investigate", "10": "Demand", "11": "Disapprove",
    "12": "Reject", "13": "Threaten", "14": "Protest", "15": "Exhibit military posture",
    "16": "Reduce relations", "17": "Coerce", "18": "Assault", "19": "Fight",
    "20": "Use unconventional mass violence",
}
# QuadClass is a deterministic function of the root code in CAMEO.
ROOT_QUAD = {r: (1 if int(r) <= 5 else 2 if int(r) <= 9 else 3 if int(r) <= 14 else 4) for r in ROOTS}
QUAD_LABELS = {1: "Verbal cooperation", 2: "Material cooperation", 3: "Verbal conflict", 4: "Material conflict"}

# Seven families a non-specialist can read. Membership is a declared mapping of
# CAMEO roots, versioned with FAMILY_VERSION; it is used for display and for
# low-volume country compositions, never to relabel GDELT records.
FAMILY_VERSION = "cameo-families-v1"
FAMILIES: list[dict[str, Any]] = [
    {"id": "statements", "label": "Statements", "roots": ["01", "02"],
     "plain": "public statements and appeals", "color": "#8a9bb4"},
    {"id": "diplomacy", "label": "Diplomacy", "roots": ["03", "04", "05"],
     "plain": "meetings, talks and diplomatic cooperation", "color": "#4f9fd6"},
    {"id": "cooperation", "label": "Aid & cooperation", "roots": ["06", "07", "08", "09"],
     "plain": "material cooperation, aid, concessions and investigations", "color": "#3fb59a"},
    {"id": "disputes", "label": "Criticism & threats", "roots": ["10", "11", "12", "13"],
     "plain": "demands, criticism, rejections and threats", "color": "#e3b04b"},
    {"id": "protest", "label": "Protests", "roots": ["14"],
     "plain": "protests, demonstrations and strikes", "color": "#e07b39"},
    {"id": "coercion", "label": "Coercion", "roots": ["15", "16", "17"],
     "plain": "military posturing, sanctions, arrests and repression", "color": "#d1495b"},
    {"id": "violence", "label": "Violence", "roots": ["18", "19", "20"],
     "plain": "assaults, armed fighting and mass violence", "color": "#9b2335"},
]
ROOT_FAMILY = {root: index for index, family in enumerate(FAMILIES) for root in family["roots"]}
assert sorted(ROOT_FAMILY) == ROOTS, "every CAMEO root belongs to exactly one family"


def roots_to_families(root_counts):
    """Collapse 20 root counts to the 7 declared families."""
    out = [0.0] * len(FAMILIES)
    for index, value in enumerate(root_counts):
        out[ROOT_FAMILY[ROOTS[index]]] += value
    return out


@lru_cache(maxsize=1)
def cameo_codes() -> dict[str, str]:
    """All CAMEO event codes (2-4 digits) with GDELT's official descriptions."""
    codes: dict[str, str] = {}
    path = REFERENCE_DIR / "CAMEO.eventcodes.txt"
    for line in path.read_text(encoding="utf-8").splitlines()[1:]:
        if "\t" in line:
            code, label = line.split("\t", 1)
            codes[code.strip()] = label.strip()
    return codes


# GDELT's lookup file carries a few mis-encoded curly quotes ("ÒhirdÓ" for "third").
_LABEL_FIXES = {"ÒhirdÓ": '"third" ', "Ò": '"', "Ó": '"'}


def base_code_label(code: str) -> str:
    label = cameo_codes().get(code)
    for broken, fixed in _LABEL_FIXES.items():
        label = label.replace(broken, fixed) if label else label
    if label is None:
        return f"CAMEO {code}"
    return label[:1].upper() + label[1:].lower() if label.isupper() else label


# --------------------------------------------------------------------------
# Places
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Place:
    iso3: str
    iso2: str
    iso_numeric: str
    name: str
    continent: str
    population: int
    area_km2: float
    capital: str
    fips: tuple[str, ...]
    neighbours: tuple[str, ...] = field(default=())


CONTINENTS = {"AF": "Africa", "AS": "Asia", "EU": "Europe", "NA": "North America",
              "SA": "South America", "OC": "Oceania", "AN": "Antarctica"}

# Display-name overrides for names GeoNames renders formally or ambiguously.
NAME_OVERRIDES = {
    "PSE": "Palestine", "COD": "DR Congo", "COG": "Congo-Brazzaville", "PRK": "North Korea",
    "KOR": "South Korea", "CIV": "Ivory Coast", "MMR": "Myanmar", "MKD": "North Macedonia",
    "CZE": "Czechia", "SWZ": "Eswatini", "CPV": "Cape Verde", "TLS": "Timor-Leste",
    "VAT": "Vatican City", "FSM": "Micronesia", "BES": "Caribbean Netherlands",
    "LAO": "Laos", "SYR": "Syria", "IRN": "Iran", "RUS": "Russia", "VNM": "Vietnam",
    "BOL": "Bolivia", "VEN": "Venezuela", "TZA": "Tanzania", "MDA": "Moldova",
    "GBR": "United Kingdom", "USA": "United States", "ARE": "United Arab Emirates",
}
# FIPS codes GeoNames does not attach to an ISO country (it lists only one FIPS per row).
EXTRA_FIPS = {"GZ": "PSE", "RB": "SRB"}


@lru_cache(maxsize=1)
def places() -> dict[str, Place]:
    rows = []
    for line in (REFERENCE_DIR / "geonames_countryInfo.txt").read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        rows.append(line.split("\t"))
    iso2_to_iso3 = {r[0]: r[1] for r in rows}
    result: dict[str, Place] = {}
    for r in rows:
        iso2, iso3, numeric, fips, name, capital, area, population, continent = r[:9]
        neighbours = tuple(iso2_to_iso3[n] for n in (r[17].split(",") if len(r) > 17 and r[17] else []) if n in iso2_to_iso3)
        fips_codes = tuple(c for c in [fips] + [f for f, iso in EXTRA_FIPS.items() if iso == iso3] if c)
        result[iso3] = Place(
            iso3=iso3, iso2=iso2, iso_numeric=numeric.zfill(3) if numeric and numeric != "0" else "",
            name=NAME_OVERRIDES.get(iso3, name.strip()), continent=CONTINENTS.get(continent, continent),
            population=int(population or 0), area_km2=float(area or 0), capital=capital.strip(),
            fips=fips_codes, neighbours=neighbours)
    return result


@lru_cache(maxsize=1)
def fips_to_iso3() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for place in places().values():
        for code in place.fips:
            mapping.setdefault(code, place.iso3)
    return mapping


@lru_cache(maxsize=1)
def fips_names() -> dict[str, str]:
    names = {}
    for line in (REFERENCE_DIR / "FIPS.country.txt").read_text(encoding="utf-8").splitlines():
        if "\t" in line:
            code, label = line.split("\t", 1)
            names[code.strip()] = label.strip()
    return names


# CAMEO actor country codes that are not ISO alpha-3 countries.
CAMEO_ACTOR_ALIASES = {"WSB": "PSE", "GZS": "PSE", "PSE": "PSE", "BAG": "IRQ", "KOS": "XKX", "ROM": "ROU", "TMP": "TLS", "ZAR": "COD"}


def actor_country(code: str) -> str | None:
    """Map a CAMEO actor country code to ISO3; regions (AFR, EUR, ...) map to None."""
    if not code:
        return None
    code = CAMEO_ACTOR_ALIASES.get(code, code)
    return code if code in places() else None


def place_name(iso3: str) -> str:
    place = places().get(iso3)
    return place.name if place else iso3
