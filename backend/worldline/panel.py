"""Assemble daily aggregates into dense, calendar-aligned arrays for modeling.

Every calendar day between the first and last stored day gets a row. Days that
are missing, partial or provider outages are present but `usable=False`, so a
gap can never be mistaken for a quiet day.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np

from .ingest import usable as is_usable
from .reference import FAMILIES, ROOT_FAMILY, ROOTS, actor_country, fips_to_iso3

FAMILY_MATRIX = np.zeros((len(ROOTS), len(FAMILIES)))
for _i, _root in enumerate(ROOTS):
    FAMILY_MATRIX[_i, ROOT_FAMILY[_root]] = 1.0
CONFLICT_FAMILIES = [i for i, f in enumerate(FAMILIES) if f["id"] in ("coercion", "violence")]
VIOLENCE_FAMILY = next(i for i, f in enumerate(FAMILIES) if f["id"] == "violence")


@dataclass
class Panel:
    dates: list[str]
    weekdays: np.ndarray            # (T,) Monday=0
    usable: np.ndarray              # (T,) bool
    partial: np.ndarray             # (T,) bool: stored but incomplete (e.g. today so far)
    slots: np.ndarray               # (T,) fifteen-minute slots represented
    total: np.ndarray               # (T,) fresh events
    roots: np.ndarray               # (T, 20) global fresh events by CAMEO root
    base_codes: list[str]
    base: np.ndarray                # (T, B) global fresh events by CAMEO base code
    countries: list[str]            # ISO3 codes
    c_roots: np.ndarray             # (T, C, 20)
    c_total: np.ndarray             # (T, C)
    c_gold: np.ndarray              # (T, C) Goldstein sum (revision-stable)
    domains: list[dict]             # per day: top publisher domains -> article count
    domains_unique: np.ndarray      # (T,)
    unmapped_fips: dict[str, int] = field(default_factory=dict)
    records: dict[str, dict] = field(default_factory=dict, repr=False)

    @property
    def T(self) -> int:
        return len(self.dates)

    def index(self, day: str) -> int:
        return self.dates.index(day)

    @property
    def families(self) -> np.ndarray:
        return self.roots @ FAMILY_MATRIX

    @property
    def c_families(self) -> np.ndarray:
        return self.c_roots @ FAMILY_MATRIX


def calendar(first: str, last: str) -> list[str]:
    start, end = date.fromisoformat(first), date.fromisoformat(last)
    return [(start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]


def build_panel(records: dict[str, dict], *, include_partial: bool = True) -> Panel:
    if not records:
        raise ValueError("no day records")
    dates = calendar(min(records), max(records))
    T = len(dates)
    fips = fips_to_iso3()
    countries = sorted({fips[c] for r in records.values() for c in r.get("geo", {}) if c in fips})
    cindex = {c: i for i, c in enumerate(countries)}
    base_codes = sorted({code for r in records.values() for code in r.get("base", {})})
    bindex = {c: i for i, c in enumerate(base_codes)}
    usable = np.zeros(T, bool)
    partial = np.zeros(T, bool)
    slots = np.zeros(T, int)
    total = np.zeros(T)
    roots = np.zeros((T, 20))
    base = np.zeros((T, len(base_codes)))
    c_roots = np.zeros((T, len(countries), 20), dtype=np.float32)
    c_total = np.zeros((T, len(countries)))
    c_gold = np.zeros((T, len(countries)))
    domains: list[dict] = [{} for _ in range(T)]
    domains_unique = np.zeros(T)
    unmapped: dict[str, int] = {}
    for t, day in enumerate(dates):
        record = records.get(day)
        if not record or record.get("gap"):
            continue
        ok = is_usable(record)
        if not ok and not include_partial:
            continue
        usable[t] = ok
        partial[t] = not ok
        slots[t] = record.get("provenance", {}).get("slots", 0) or 0
        total[t] = record["fresh"]
        roots[t] = record["root"]
        for code, n in record.get("base", {}).items():
            base[t, bindex[code]] = n
        for code, stats in record.get("geo", {}).items():
            iso = fips.get(code)
            if iso is None:
                unmapped[code] = unmapped.get(code, 0) + stats["n"]
                continue
            j = cindex[iso]
            c_roots[t, j] += np.asarray(stats["root"], dtype=np.float32)
            c_total[t, j] += stats["n"]
            c_gold[t, j] += stats["gold"]
        domains[t] = record.get("domains", {})
        domains_unique[t] = record.get("domains_unique", 0)
    weekdays = np.array([date.fromisoformat(d).weekday() for d in dates])
    return Panel(dates=dates, weekdays=weekdays, usable=usable, partial=partial, slots=slots, total=total,
                 roots=roots, base_codes=base_codes, base=base, countries=countries, c_roots=c_roots,
                 c_total=c_total, c_gold=c_gold, domains=domains, domains_unique=domains_unique,
                 unmapped_fips=unmapped, records=records)


def dyad_matrix(records: dict[str, dict], days: list[str], countries: list[str]) -> np.ndarray:
    """Sum actor-country interactions over `days`: array (C, C, 4) by QuadClass, actor1 -> actor2."""
    cindex = {c: i for i, c in enumerate(countries)}
    out = np.zeros((len(countries), len(countries), 4))
    for day in days:
        record = records.get(day)
        if not record or not is_usable(record):
            continue
        for key, quads in record.get("dyad", {}).items():
            a, b = key.split(">")
            ia, ib = actor_country(a), actor_country(b)
            if ia in cindex and ib in cindex:
                out[cindex[ia], cindex[ib]] += quads
    return out
