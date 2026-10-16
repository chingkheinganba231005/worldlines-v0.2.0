"""The monitor's three promises: no look-ahead, honest p-values on quiet data, and real breaks get caught."""
import numpy as np
import pytest

from synthetic import make_records
from worldline.monitor import Config, country_monitor, global_monitor, instrument_status, prequential
from worldline.panel import build_panel

CFG = Config()


@pytest.fixture(scope="module")
def quiet(synthetic):
    records, _ = synthetic
    panel = build_panel(records)
    instrument = global_monitor(panel, CFG)["instrument"]
    return panel, instrument, country_monitor(panel, CFG, instrument)


def test_prequential_forecasts_use_only_the_past():
    rng = np.random.default_rng(0)
    T = 300
    y = rng.normal(size=(T, 1)).cumsum(0) * 0.1 + rng.normal(size=(T, 1))
    valid = np.ones(T, bool)
    weekdays = np.arange(T) % 7
    pred, fitted_at = prequential(y, valid, weekdays, CFG)
    changed = y.copy()
    changed[200:] += 50.0  # a huge change from day 200 on
    pred2, _ = prequential(changed, valid, weekdays, CFG)
    assert np.allclose(pred[:200], pred2[:200], equal_nan=True)
    assert np.all(fitted_at[np.isfinite(pred[:, 0])] <= np.flatnonzero(np.isfinite(pred[:, 0])))


def test_no_leakage_into_earlier_days(synthetic, quiet):
    """Scores for day t must not change when every later day is removed."""
    records, _ = synthetic
    panel, _, full = quiet
    cut = 400
    truncated = build_panel({d: r for d, r in records.items() if d < panel.dates[cut]})
    instrument = global_monitor(truncated, CFG)["instrument"]
    early = country_monitor(truncated, CFG, instrument)
    assert early["countries"] == full["countries"]
    for key in ("p_attention", "p_mix", "p_conflict", "p_articles", "p_combined", "articles_pred"):
        assert np.allclose(early[key], full[key][:cut], equal_nan=True, rtol=0, atol=1e-12), key


def test_p_values_are_calibrated_when_nothing_happens(quiet):
    _, _, scores = quiet
    for key in ("p_attention", "p_mix", "p_conflict", "p_articles", "p_combined"):
        p = scores[key][np.isfinite(scores[key])]
        assert p.size > 4000
        assert 0.025 <= np.mean(p <= 0.05) <= 0.07, key
        assert np.mean(p <= 0.01) <= 0.02, key
    # With 24 countries scored daily, about 1.2 "1-in-20-days" readings are expected per day by chance.
    turbulence = scores["turbulence"][np.isfinite(scores["turbulence"])]
    assert abs(turbulence.mean() - scores["turbulence_expected"][np.isfinite(scores["turbulence"])].mean()) < 0.6


def test_an_injected_break_is_caught(synthetic_spike):
    records, _ = synthetic_spike
    panel = build_panel(records)
    instrument = global_monitor(panel, CFG)["instrument"]
    scores = country_monitor(panel, CFG, instrument)
    m = scores["countries"].index("SDN")
    t = panel.index("2024-02-15")  # day 410
    assert scores["p_combined"][t, m] < 1e-3
    assert scores["p_conflict"][t, m] < 1e-3 and scores["p_attention"][t, m] < 1e-3
    assert scores["tier"][t, m] >= 2 and scores["alarm"][t, m] and scores["fdr_significant"][t, m]
    assert scores["conflict_obs"][t, m] > 2 * scores["conflict_exp"][t, m]
    # Nobody else alarms that day, and Sudan was quiet the week before.
    others = [k for k in range(len(scores["countries"])) if k != m]
    assert not scores["fdr_significant"][t, others].any()
    assert np.nanmin(scores["p_combined"][t - 7:t, m]) > 1e-3


def test_degraded_instrument_days_are_flagged_and_not_scored():
    records, _ = make_records(days=420)
    day = sorted(records)[400]
    broken = dict(records[day])
    broken["fresh"] = int(broken["fresh"] * 0.2)  # ingestion fault: a fifth of the usual volume
    broken["domains"] = {"onlyone.example": 500}   # and a publisher mix unlike any normal day
    records[day] = broken
    panel = build_panel(records)
    status = instrument_status(panel, CFG)
    t = panel.index(day)
    assert status["degraded"][t]
    assert status["volume_ratio"][t] < CFG.instrument_min_ratio and status["source_js"][t] > CFG.instrument_max_source_js
    scores = country_monitor(panel, CFG, status)
    assert np.all(np.isnan(scores["p_combined"][t])) and not scores["alarm"][t].any()


def test_gaps_are_not_quiet_days(synthetic):
    records, _ = synthetic
    days = sorted(records)
    holey = {d: r for d, r in records.items() if d not in days[300:303]}
    holey[days[301]] = {"date": days[301], "gap": True, "provenance": {"kind": "unavailable"}}
    panel = build_panel(holey)
    assert panel.T == len(days)
    assert not panel.usable[300:303].any()
    assert panel.total[300:303].sum() == 0  # present as rows, flagged unusable rather than imputed
