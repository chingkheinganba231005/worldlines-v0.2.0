"""Write the static site's data: a versioned, documented JSON API plus an RSS feed of alarms.

Everything the browser shows is computed here; the client never invents a number.
"""
from __future__ import annotations

import html
import json
import math
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np

from .embeddings import check_event_embeddings, project_2d
from .experiments import published_pvalues
from .monitor import TIER_NAMES
from .panel import CONFLICT_FAMILIES
from .reference import FAMILIES, FAMILY_VERSION, ROOT_FAMILY, ROOT_QUAD, base_code_label, fips_to_iso3, place_name, places

API_VERSION = "2"
TIER_LABELS = {1: "Unusual", 2: "Rare", 3: "Extreme"}
FAMILY_VERB = {"statements": "Statements make up", "diplomacy": "Diplomacy makes up", "cooperation": "Aid & cooperation make up",
               "disputes": "Criticism & threats make up", "protest": "Protests make up", "coercion": "Coercion makes up",
               "violence": "Violence makes up"}
WORLDLINE_MIN_VOLUME = 1500  # dyadic events in a 3-month window: below this, monthly positions are mostly sampling noise
RP_CAP = 5000


def _f(value, digits=4):
    if value is None:
        return None
    value = float(value)
    return None if not math.isfinite(value) else round(value, digits)


def _write(path: Path, payload) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    path.write_text(text, encoding="utf-8")
    return len(text)


def flag(iso2: str) -> str:
    return "".join(chr(0x1F1E6 + ord(c) - 65) for c in iso2.upper()) if len(iso2) == 2 and iso2.isalpha() else ""


def return_period(p: float | None) -> float | None:
    if p is None or not np.isfinite(p) or p <= 0:
        return None
    return min(1.0 / p, RP_CAP)


def rp_text(p: float | None) -> str:
    period = return_period(p)
    if period is None:
        return "—"
    if period >= RP_CAP:
        return f"1-in-{RP_CAP:,}+ days"
    return f"1-in-{period:,.0f} days"


class Publisher:
    def __init__(self, analysis, model: dict, labels: list[dict], evidence: dict, records: dict, scenarios: dict | None):
        self.a = analysis
        self.panel = analysis.panel
        self.c = analysis.country
        self.model = model
        self.labels = labels
        self.evidence = evidence
        self.records = records
        self.scenarios = scenarios
        self.p = published_pvalues(self.c, model)
        self.degraded = analysis.global_["instrument"]["degraded"]
        gate = (self.c["outlets"] >= model["min_outlets"]) & ~self.degraded[:, None]
        periods = np.where(np.isfinite(self.p), 1 / np.clip(self.p, 1e-12, 1), 0)
        tiers = np.zeros(self.p.shape, dtype=int)
        for k, threshold in enumerate(analysis.cfg.tiers, 1):
            tiers[periods >= threshold] = k
        self.tier = np.where(gate, tiers, 0)
        self.u = -np.log10(np.clip(self.p, 1e-12, 1))
        scored = np.isfinite(self.p).any(1)
        self.last = int(np.flatnonzero(scored & self.panel.usable)[-1])
        self.countries = self.c["countries"]
        self.member_index = {c: i for i, c in enumerate(self.countries)}
        self.fips_for: dict[str, list[str]] = {}
        for fips, iso in fips_to_iso3().items():
            self.fips_for.setdefault(iso, []).append(fips)
        self.labels_by_country: dict[str, list[dict]] = {}
        for event in labels:
            for iso in event["countries"]:
                self.labels_by_country.setdefault(iso, []).append(event)
        self.label_ids_by_date: dict[str, list[str]] = {}
        for event in labels:
            self.label_ids_by_date.setdefault(event["date"], []).append(event["id"])

    # ------------------------------------------------------------------ helpers
    def turbulence(self):
        count = np.sum(self.p <= 0.05, axis=1).astype(float)
        scored = np.sum(np.isfinite(self.p), axis=1)
        expected = 0.05 * scored
        count[scored == 0] = np.nan
        expected[scored == 0] = np.nan
        return count, expected

    def evidence_for(self, iso3: str, day: str, limit: int = 3) -> list[dict]:
        record = self.evidence.get(day)
        if not record:
            return []
        entries = []
        for fips in self.fips_for.get(iso3, []):
            for index, count in record.get("top", {}).get(fips, []):
                url = record["urls"][index]
                if url.startswith(("http://", "https://")):
                    domain = url.split("/", 3)[2].lower()
                    entries.append({"url": url, "domain": domain[4:] if domain.startswith("www.") else domain, "events": count})
        entries.sort(key=lambda e: -e["events"])
        return entries[:limit]

    def top_codes(self, iso3: str, day: str, limit: int = 4) -> list[dict]:
        record = self.records.get(day)
        if not record:
            return []
        merged: dict[str, int] = {}
        for fips in self.fips_for.get(iso3, []):
            for code, n in record.get("geo", {}).get(fips, {}).get("top", []):
                merged[code] = merged.get(code, 0) + n
        return [{"code": code, "label": base_code_label(code), "events": n,
                 "family": FAMILIES[ROOT_FAMILY[code[:2]]]["id"]} for code, n in sorted(merged.items(), key=lambda kv: -kv[1])[:limit]]

    def wikipedia_near(self, iso3: str, t: int) -> list[dict]:
        days = {self.panel.dates[s] for s in range(max(0, t - 2), min(self.panel.T, t + 2))}
        return [{"date": e["date"], "text": e["text"], "id": e["id"]} for e in self.labels_by_country.get(iso3, []) if e["date"] in days][:3]

    def drivers(self, t: int, m: int) -> list[dict]:
        c = self.c
        out = []
        p_art = c["p_articles"][t, m]
        if np.isfinite(p_art):
            ratio = c["article_ratio"][t, m]
            text = (f"Coverage is {ratio:.1f}× its usual share of world news" if ratio >= 1.1 else
                    f"Coverage is {ratio:.2f}× its usual share of world news — quieter than usual" if ratio <= 0.9 else
                    "Coverage is about its usual share of world news")
            out.append({"channel": "attention", "p": _f(p_art, 6), "ratio": _f(ratio, 2), "text": text})
        p_mix = c["p_mix"][t, m]
        if np.isfinite(p_mix):
            observed, forecast = c["mix_observed"][t, m], c["mix_forecast"][t, m]
            if np.all(np.isfinite(forecast)):
                # The family that gained the most percentage points: what a reader would notice first.
                k = int(np.argmax(observed - forecast))
                family = FAMILIES[k]
                out.append({"channel": "mix", "p": _f(p_mix, 6), "family": family["id"], "observed": _f(observed[k], 3),
                            "expected": _f(forecast[k], 3),
                            "text": f"{FAMILY_VERB[family['id']]} {observed[k]:.0%} of reports (usually about {forecast[k]:.0%})"})
        p_con = c["p_conflict"][t, m]
        if np.isfinite(p_con):
            obs, exp = c["conflict_obs"][t, m], c["conflict_exp"][t, m]
            out.append({"channel": "conflict", "p": _f(p_con, 6), "observed": _f(obs, 3), "expected": _f(exp, 3),
                        "text": f"Coercion and violence are {obs:.0%} of reports (usually about {exp:.0%})"})
        out.sort(key=lambda d: d["p"] if d["p"] is not None else 1)
        return out

    def country_day(self, t: int, m: int, *, rich: bool = True) -> dict:
        iso3 = self.countries[m]
        place = places().get(iso3)
        day = self.panel.dates[t]
        p = self.p[t, m]
        out = {"iso3": iso3, "name": place_name(iso3), "flag": flag(place.iso2) if place else "", "date": day,
               "tier": int(self.tier[t, m]), "tier_label": TIER_LABELS.get(int(self.tier[t, m]), "None"),
               "p": _f(p, 8), "return_period": _f(return_period(p), 0), "return_period_text": rp_text(p),
               "unusualness": _f(self.u[t, m], 3),
               "events": int(self.c["events"][t, m]), "articles": int(self.c["articles"][t, m]),
               "outlets": int(self.c["outlets"][t, m])}
        if rich:
            out["drivers"] = self.drivers(t, m)
            out["evidence"] = self.evidence_for(iso3, day)
            out["top_codes"] = self.top_codes(iso3, day)
            out["wikipedia"] = self.wikipedia_near(iso3, t)
        return out

    # ------------------------------------------------------------------ outputs
    def latest(self, nowcast: dict | None, generated_at: str) -> dict:
        t = self.last
        count, expected = self.turbulence()
        history = count[max(0, t - 365):t + 1]
        history = history[np.isfinite(history)]
        percentile = float(100 * np.mean(history <= count[t])) if len(history) else None
        if percentile is None:
            label = "Typical"  # no scored history yet: make no claim either way
        else:
            label = ("Calm" if percentile < 50 else "Typical" if percentile < 80 else
                     "Busy" if percentile < 95 else "Turbulent" if percentile < 99 else "Exceptional")
        ranked = [m for m in np.argsort(self.p[t]) if np.isfinite(self.p[t, m])]
        alarms = [self.country_day(t, m) for m in ranked if self.tier[t, m] > 0]
        watch = [self.country_day(t, m, rich=False) | {"drivers": self.drivers(t, m)[:1]} for m in ranked[:12]]
        g = self.a.global_
        fam = self.panel.families
        dev = np.array([d <= self.a.cfg.dev_end for d in self.panel.dates]) & self.panel.usable
        typical_shares = (fam[dev] / fam[dev].sum(1, keepdims=True)).mean(0)
        recent = []
        for s in range(max(0, t - 13), t + 1):
            members = [m for m in np.argsort(self.p[s]) if self.tier[s, m] > 0]
            recent.append({"date": self.panel.dates[s], "turbulence": _f(count[s], 0), "expected": _f(expected[s], 1),
                           "alarms": [{"iso3": self.countries[m], "name": place_name(self.countries[m]), "tier": int(self.tier[s, m]),
                                       "return_period": _f(return_period(self.p[s, m]), 0)} for m in members[:8]]})
        mix_p = g["mix"]["p"][t]
        ratio = count[t] / expected[t] if expected[t] else None
        brief = self.brief(t, alarms, count[t], expected[t], label, fam[t] / max(fam[t].sum(), 1), typical_shares)
        return {
            "api": API_VERSION, "generated_at": generated_at, "date": self.panel.dates[t],
            "pulse": {"label": label, "turbulence": _f(count[t], 0), "expected": _f(expected[t], 1), "ratio": _f(ratio, 2),
                      "percentile_365": _f(percentile, 1), "scored_countries": int(np.isfinite(self.p[t]).sum()),
                      "global_mix_p": _f(mix_p, 6), "global_mix_return_period": _f(return_period(mix_p), 0),
                      "global_mix_text": rp_text(mix_p)},
            "brief": brief, "alarms": alarms, "watchlist": watch, "recent": recent,
            "mix": {"families": [f["id"] for f in FAMILIES], "today": [_f(v, 4) for v in fam[t] / max(fam[t].sum(), 1)],
                    "typical": [_f(v, 4) for v in typical_shares], "typical_label": "2023 average"},
            "displacement": {"js_frozen": _f(g["js_frozen"][t], 5), "js_rolling": _f(g["js_rolling"][t], 5),
                             "ot_frozen": _f(self.a.transport["ot_frozen"][t], 5), "ot_rolling": _f(self.a.transport["ot_rolling"][t], 5),
                             "js_dev_median": _f(g["js_dev_median"], 5), "ot_dev_median": _f(self.a.transport["ot_dev_median"], 5)},
            "instrument": self.instrument(t), "nowcast": nowcast,
        }

    def instrument(self, t: int) -> dict:
        inst = self.a.global_["instrument"]
        record = self.records.get(self.panel.dates[t], {})
        return {"degraded": bool(self.degraded[t]), "volume_ratio": _f(inst["volume_ratio"][t], 3),
                "source_js": _f(inst["source_js"][t], 4), "events": int(self.panel.total[t]),
                "articles": int(self.panel.urls[t]), "outlets": int(self.panel.domains_unique[t]),
                "provenance": {k: record.get("provenance", {}).get(k) for k in ("kind", "slots", "md5", "transfer_verified", "listed_md5_match", "retrieved_at")}}

    def brief(self, t, alarms, count, expected, label, today_shares, typical_shares) -> list[str]:
        lines = []
        if expected and np.isfinite(count):
            ratio = count / expected
            if ratio >= 1.3:
                lines.append(f"{int(count)} of {int(np.isfinite(self.p[t]).sum())} monitored countries look unusual today — "
                             f"{ratio:.1f}× what chance alone would produce.")
            else:
                lines.append(f"{int(count)} of {int(np.isfinite(self.p[t]).sum())} monitored countries look unusual today — about what "
                             f"chance alone would produce (~{expected:.0f}).")
        for alarm in alarms[:3]:
            driver = alarm["drivers"][0]["text"] if alarm["drivers"] else "Unusual reporting"
            lines.append(f"{alarm['name']}: {driver}. A {alarm['return_period_text'].replace(' days', '-day')} event for "
                         f"{alarm['name']} ({alarm['articles']:,} articles, {alarm['outlets']:,} outlets).")
        if not alarms:
            lines.append("No country crossed the alarm threshold (a 1-in-100-days event with at least 20 outlets reporting).")
        violence = FAMILIES.index(next(f for f in FAMILIES if f["id"] == "violence"))
        lines.append(f"Worldwide, violence makes up {today_shares[violence]:.1%} of machine-coded events "
                     f"(2023 average {typical_shares[violence]:.1%}).")
        return lines

    def timeline(self) -> dict:
        count, expected = self.turbulence()
        g = self.a.global_
        T = self.last + 1
        tiers = [[int(v) for v in np.sum(self.tier[:T] == k, axis=1)] for k in (1, 2, 3)]
        top = []
        for t in range(T):
            members = [m for m in np.argsort(self.p[t]) if self.tier[t, m] > 0][:4]
            top.append([self.countries[m] for m in members])
        return {"api": API_VERSION, "dates": self.panel.dates[:T],
                "turbulence": [_f(v, 0) for v in count[:T]], "expected": [_f(v, 2) for v in expected[:T]],
                "global_mix_u": [_f(-math.log10(max(p, 1e-12)), 3) if np.isfinite(p) else None for p in g["mix"]["p"][:T]],
                "js_rolling": [_f(v, 5) for v in g["js_rolling"][:T]], "ot_rolling": [_f(v, 5) for v in self.a.transport["ot_rolling"][:T]],
                "js_frozen": [_f(v, 5) for v in g["js_frozen"][:T]],
                "degraded": [bool(v) for v in self.degraded[:T]], "usable": [bool(v) for v in self.panel.usable[:T]],
                "events": [int(v) for v in self.panel.total[:T]],
                "alarms": {"unusual": tiers[0], "rare": tiers[1], "extreme": tiers[2]}, "top": top,
                "labels": [self.label_ids_by_date.get(d, []) for d in self.panel.dates[:T]]}

    def grid(self) -> dict:
        T = self.last + 1
        u10 = np.where(np.isfinite(self.u[:T]), np.round(np.minimum(self.u[:T], 9.9) * 10), -1).astype(int)
        return {"api": API_VERSION, "countries": self.countries, "dates": self.panel.dates[:T], "scale": "unusualness x10 (-log10 p)",
                "u10": u10.tolist(), "tier": self.tier[:T].tolist()}

    def countries_index(self) -> list[dict]:
        t = self.last
        out = []
        for m, iso3 in enumerate(self.countries):
            place = places().get(iso3)
            alarms = np.flatnonzero(self.tier[:t + 1, m] > 0)
            spark = self.u[max(0, t - 89):t + 1, m]
            out.append({"iso3": iso3, "iso2": place.iso2 if place else "", "flag": flag(place.iso2) if place else "",
                        "name": place_name(iso3), "continent": place.continent if place else "",
                        "population": place.population if place else None,
                        "unusualness": _f(self.u[t, m], 3), "tier": int(self.tier[t, m]), "p": _f(self.p[t, m], 8),
                        "return_period_text": rp_text(self.p[t, m]),
                        "events": int(self.c["events"][t, m]), "article_ratio": _f(self.c["article_ratio"][t, m], 2),
                        "spark": [None if not np.isfinite(v) else round(float(min(v, 9.9)), 2) for v in spark],
                        "alarms_365": int(np.sum(alarms > t - 365)), "last_alarm": self.panel.dates[alarms[-1]] if len(alarms) else None})
        return out

    def country(self, m: int, worldline: dict | None) -> dict:
        iso3 = self.countries[m]
        place = places().get(iso3)
        T = self.last + 1
        fam = self.panel.c_families[:T, self.panel.countries.index(iso3), :]
        shares = np.round(1000 * fam / np.maximum(fam.sum(1, keepdims=True), 1)).astype(int)
        alarm_days = np.flatnonzero(self.tier[:T, m] > 0)
        alarms = [self.country_day(t, m) for t in alarm_days[::-1][:60]]
        c = self.c
        partners = self.partners(iso3, max(0, T - 30), T)
        return {"api": API_VERSION, "iso3": iso3, "iso2": place.iso2 if place else "", "flag": flag(place.iso2) if place else "",
                "name": place_name(iso3), "continent": place.continent if place else "", "population": place.population if place else None,
                "capital": place.capital if place else "", "neighbours": [n for n in (place.neighbours if place else []) if n in self.member_index],
                "first_date": self.panel.dates[0],
                "series": {"u": [_f(v, 2) for v in self.u[:T, m]], "tier": [int(v) for v in self.tier[:T, m]],
                           "events": [int(v) for v in c["events"][:T, m]], "articles": [int(v) for v in c["articles"][:T, m]],
                           "outlets": [int(v) for v in c["outlets"][:T, m]],
                           "article_ratio": [_f(v, 2) for v in c["article_ratio"][:T, m]],
                           "conflict_obs": [_f(v, 3) for v in c["conflict_obs"][:T, m]],
                           "conflict_exp": [_f(v, 3) for v in c["conflict_exp"][:T, m]],
                           "families_permille": shares.tolist()},
                "today": self.country_day(self.last, m), "alarms": alarms,
                "labels": [{"date": e["date"], "text": e["text"], "categories": e["categories"]} for e in self.labels_by_country.get(iso3, [])],
                "partners": partners, "worldline": worldline}

    def partners(self, iso3: str, start: int, end: int, limit: int = 8) -> list[dict]:
        from .reference import actor_country
        totals: dict[str, list[int]] = {}
        for t in range(start, end):
            record = self.records.get(self.panel.dates[t])
            if not record:
                continue
            for key, quads in record.get("dyad", {}).items():
                a, b = key.split(">")
                ia, ib = actor_country(a), actor_country(b)
                if ia == iso3 and ib and ib != iso3:
                    other = ib
                elif ib == iso3 and ia and ia != iso3:
                    other = ia
                else:
                    continue
                acc = totals.setdefault(other, [0, 0, 0, 0])
                for q in range(4):
                    acc[q] += quads[q]
        ranked = sorted(totals.items(), key=lambda kv: -sum(kv[1]))[:limit]
        return [{"iso3": k, "name": place_name(k), "events": sum(v), "cooperation": v[0] + v[1], "conflict": v[2] + v[3]} for k, v in ranked]

    def worldlines(self) -> tuple[dict, dict]:
        w = self.a.worldlines
        months = w["months"]
        xy = {}
        per_country = {}
        for m, iso3 in enumerate(self.countries):
            path: list[list[float] | None] = []
            for month in months:
                if w["active"][month][m]:
                    x, y = w["plane"][month][m]
                    path.append([round(float(x), 4), round(float(y), 4)])
                else:
                    path.append(None)
            xy[iso3] = path
        last = months[-1]
        pos = w["positions"][last]
        act = w["active"][last]
        for m, iso3 in enumerate(self.countries):
            if not act[m]:
                continue
            sims = pos @ pos[m]
            sims[~act] = -9
            sims[m] = -9
            order = np.argsort(-sims)[:6]
            drift: list[float | None] = []
            for a_month, b_month in zip(months, months[1:]):
                if w["active"][a_month][m] and w["active"][b_month][m]:
                    drift.append(round(float(1 - w["positions"][a_month][m] @ w["positions"][b_month][m]), 4))
                else:
                    drift.append(None)
            per_country[iso3] = {"neighbors": [{"iso3": self.countries[j], "name": place_name(self.countries[j]),
                                                "similarity": round(float(sims[j]), 3)} for j in order],
                                 "drift": drift, "months": months}
        # Net repositioning over 12 months (cosine distance in the aligned space), for countries with enough
        # relational data that a monthly position is more signal than sampling noise.
        volume = w["volume"]
        repositioning = {}
        if len(months) > 12:
            then, now = months[-13], months[-1]
            for m, iso3 in enumerate(self.countries):
                if not (w["active"][then][m] and w["active"][now][m]):
                    continue
                if np.median([volume[mm][m] for mm in months[-13:]]) < WORLDLINE_MIN_VOLUME:
                    continue
                repositioning[iso3] = round(float(1 - w["positions"][then][m] @ w["positions"][now][m]), 4)
        well_measured = [iso3 for m, iso3 in enumerate(self.countries) if np.median([volume[mm][m] for mm in months[-13:]]) >= WORLDLINE_MIN_VOLUME]
        payload = {"api": API_VERSION, "months": months, "countries": [{"iso3": c, "name": place_name(c),
                   "continent": places()[c].continent if c in places() else ""} for c in self.countries],
                   "xy": xy, "repositioning": repositioning, "well_measured": well_measured, "checks": self.a.worldlines_check,
                   "method": "PPMI + truncated SVD of partner x direction x QuadClass interaction counts (3-month windows), "
                             "aligned to a whole-period anchor by orthogonal Procrustes; plane = first two principal axes."}
        return payload, per_country

    def event_space(self) -> dict:
        model = self.a.events_model
        xy, _ = project_2d(model["vectors"])
        codes = []
        for i, code in enumerate(model["codes"]):
            family = FAMILIES[ROOT_FAMILY[code[:2]]]
            codes.append({"code": code, "label": base_code_label(code), "family": family["id"], "quad": ROOT_QUAD[code[:2]],
                          "x": round(float(xy[i, 0]), 4), "y": round(float(xy[i, 1]), 4), "events_2023": int(model["counts"][i])})
        return {"api": API_VERSION, "version": model["version"], "codes": codes, "checks": self.a.events_check,
                "training": model["training"]}

    def scenarios_payload(self) -> dict | None:
        s = self.scenarios
        if not s:
            return None
        H = min(21, s["horizon"])
        def arr(a):
            return np.round(a[:, :H + 1, :], 4).tolist()
        skill = s["skill"]
        conn = s["connectedness"]
        return {"api": API_VERSION, "version": s["version"], "countries": [{"iso3": c, "name": place_name(c)} for c in s["countries"]],
                "horizon": H, "units": "log(1 + conflict events) response to a +1 log-unit (×2.72) shock; scale linearly for other shocks",
                "median": arr(s["bands"][1]), "lo": arr(s["bands"][0]), "hi": arr(s["bands"][2]),
                "connectedness": {"total": round(conn["total"], 2), "to": [round(float(v), 2) for v in conn["to"]],
                                  "from": [round(float(v), 2) for v in conn["from"]], "net": [round(float(v), 2) for v in conn["net"]]},
                "rolling": [{"month": r["month"], "total": round(r["total"], 2)} for r in s["rolling_connectedness"]],
                "skill": {"split": skill.get("split"), "test_days": skill.get("test_days"),
                          "mean_improvement_pct": _f(skill.get("mean_improvement_pct"), 2),
                          "improvement_pct": [_f(v, 2) for v in skill.get("improvement_pct", [])]},
                "lambda": s["lambda"], "kappa": s["kappa"], "fit_period": s["fit_period"], "observations": s["observations"]}

    def alarm_list(self, since: str) -> list[dict]:
        out = []
        for t in range(self.panel.T):
            if self.panel.dates[t] < since or t > self.last:
                continue
            for m in np.flatnonzero(self.tier[t] > 0):
                out.append({"date": self.panel.dates[t], "iso3": self.countries[m], "name": place_name(self.countries[m]),
                            "tier": int(self.tier[t, m]), "return_period": _f(return_period(self.p[t, m]), 0)})
        return out

    def feed(self, base_url: str, days: int = 60) -> str:
        items = []
        for t in range(self.last, max(-1, self.last - days), -1):
            for m in np.argsort(self.p[t]):
                if self.tier[t, m] <= 0:
                    continue
                d = self.country_day(t, m)
                title = f"{d['tier_label']}: {d['name']} — {d['return_period_text']} ({d['date']})"
                desc = "; ".join(x["text"] for x in d["drivers"][:2]) or "Unusual reporting pattern"
                link = f"{base_url}#/country/{d['iso3']}"
                pub = datetime.combine(date.fromisoformat(d["date"]), datetime.min.time(), tzinfo=timezone.utc).strftime("%a, %d %b %Y 23:59:59 +0000")
                items.append(f"<item><title>{html.escape(title)}</title><link>{html.escape(link)}</link>"
                             f"<guid isPermaLink=\"false\">worldline-{d['iso3']}-{d['date']}</guid><pubDate>{pub}</pubDate>"
                             f"<description>{html.escape(desc)}. Statistical signal in news metadata, not a verified event.</description></item>")
        return ("<?xml version=\"1.0\" encoding=\"UTF-8\"?><rss version=\"2.0\"><channel><title>WORLDLINE alarms</title>"
                f"<link>{html.escape(base_url)}</link><description>Countries whose news record became unusual (GDELT, daily).</description>"
                + "".join(items) + "</channel></rss>")


def publish_all(analysis, model: dict, labels_doc: dict, evidence: dict, records: dict, scenarios: dict | None,
                validation: dict | None, map_data: dict, out: Path, *, nowcast: dict | None = None, base_url: str = "",
                build: dict | None = None) -> dict:
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    pub = Publisher(analysis, model, labels_doc["events"], evidence, records, scenarios)
    data = out / "data"
    sizes = {}
    sizes["latest.json"] = _write(data / "latest.json", pub.latest(nowcast, generated_at))
    sizes["timeline.json"] = _write(data / "timeline.json", pub.timeline())
    sizes["grid.json"] = _write(data / "grid.json", pub.grid())
    sizes["countries.json"] = _write(data / "countries.json", {"api": API_VERSION, "date": pub.panel.dates[pub.last],
                                                               "countries": pub.countries_index()})
    worldlines, per_country = pub.worldlines()
    sizes["worldlines.json"] = _write(data / "worldlines.json", worldlines)
    total = 0
    for m, iso3 in enumerate(pub.countries):
        total += _write(data / "country" / f"{iso3}.json", pub.country(m, per_country.get(iso3)))
    sizes["country/*.json"] = total
    sizes["event_space.json"] = _write(data / "event_space.json", pub.event_space())
    scen = pub.scenarios_payload()
    if scen:
        sizes["scenarios.json"] = _write(data / "scenarios.json", scen)
    if validation:
        from .live import LAUNCH_DATE, prospective
        validation = dict(validation)
        validation["prospective"] = prospective(pub.alarm_list(LAUNCH_DATE), labels_doc["events"])
        sizes["validation.json"] = _write(data / "validation.json", validation)
    sizes["labels.json"] = _write(data / "labels.json", {"license": labels_doc["license"], "attribution": labels_doc["attribution"],
                                                        "manifest": labels_doc["manifest"],
                                                        "events": [{k: e[k] for k in ("id", "date", "text", "countries", "categories")} for e in labels_doc["events"]]})
    sizes["map.json"] = _write(data / "map.json", map_data)
    meta = {"api": API_VERSION, "name": "WORLDLINE", "version": "0.2.0", "detector": model["version"], "generated_at": generated_at,
            "data_as_of": pub.panel.dates[pub.last], "first_date": pub.panel.dates[0], "monitored": len(pub.countries),
            "tiers": [{"tier": k, "label": TIER_LABELS[k], "return_period_days": p} for k, p in enumerate(analysis.cfg.tiers, 1)],
            "min_outlets": model["min_outlets"], "weights": model["weights"],
            "families": [{k: f[k] for k in ("id", "label", "plain", "roots")} for f in FAMILIES], "family_version": FAMILY_VERSION,
            "sources": [{"name": "GDELT 2.0 Event database", "url": "https://www.gdeltproject.org/", "use": "event metadata (no article text)"},
                        {"name": "Wikipedia year articles", "url": "https://en.wikipedia.org/wiki/2025", "use": "independent validation labels (CC BY-SA 4.0)"},
                        {"name": "Natural Earth via world-atlas", "url": "https://github.com/topojson/world-atlas", "use": "map shapes (public domain)"},
                        {"name": "GeoNames", "url": "https://www.geonames.org/", "use": "country codes and names (CC BY 4.0)"}],
            "build": build or {}, "files": sizes}
    _write(data / "meta.json", meta)
    (out / "feed.xml").write_text(pub.feed(base_url or "./"), encoding="utf-8")
    return meta
