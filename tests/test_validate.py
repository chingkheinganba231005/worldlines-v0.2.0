import numpy as np
import pytest

from worldline.validate import (Labels, alarm_metrics, auc_null, calibration_on_quiet_days, circular_shift_null, label_index,
                                stratified_auc, window_max_array)


def labels_for(pairs):
    by_member = {}
    for t, m in pairs:
        by_member.setdefault(m, []).append(t)
    return Labels(sorted(pairs), {m: np.array(sorted(v)) for m, v in by_member.items()})


def test_label_index_filters_by_period_category_and_membership():
    dates = ["2024-01-01", "2024-01-02", "2024-01-03"]
    events = [{"date": "2024-01-02", "countries": ["SDN", "XXX"], "categories": ["conflict"]},
              {"date": "2024-01-02", "countries": ["SDN"], "categories": ["political"]},   # same pair: deduplicated
              {"date": "2024-01-03", "countries": ["FRA"], "categories": ["disaster"]},    # not a primary category
              {"date": "2023-12-31", "countries": ["SDN"], "categories": ["conflict"]}]    # outside the period
    out = label_index(events, dates, ["FRA", "SDN"], start="2024-01-01", end="2024-12-31")
    assert out.positives == [(1, 1)]
    assert list(out.events_by_member[1]) == [1]


def test_window_max_requires_complete_windows():
    u = np.array([[1.0], [5.0], [2.0], [0.0], [np.nan], [3.0], [0.0], [1.0], [2.0]])
    W = window_max_array(u)
    # Window for day t is [t-1, t+2].
    assert W[1, 0] == 5.0 and np.isnan(W[0, 0])  # day 0 lacks day -1
    assert np.isnan(W[2, 0])                       # contains the gap at day 4
    assert W[6, 0] == 3.0
    assert np.isnan(W[7, 0]) and np.isnan(W[8, 0])  # run past the end


def test_stratified_auc_perfect_and_random():
    T, M = 400, 3
    rng = np.random.default_rng(0)
    scored = np.ones((T, M), bool)
    test = np.ones(T, bool)
    pairs = [(t, m) for m in range(M) for t in range(20 + 7 * m, T - 20, 40)]
    labels = labels_for(pairs)
    W = rng.uniform(size=(T, M))
    for t, m in pairs:
        W[t, m] = 2.0
    auc, per_member = stratified_auc(W, scored, labels, test)
    assert auc == 1.0 and set(per_member) == {0, 1, 2}
    noise = rng.uniform(size=(T, M))
    assert stratified_auc(noise, scored, labels, test)[0] == pytest.approx(0.5, abs=0.1)
    shifted = auc_null(W, scored, labels, test, permutations=50)
    assert shifted["observed_auc"] == 1.0 and shifted["p_value"] < 0.05


def test_alarm_metrics_and_permutation_null():
    T, M = 500, 2
    test = np.ones(T, bool)
    scored = np.ones((T, M), bool)
    pairs = [(t, m) for m in range(M) for t in range(30, T - 30, 50)]
    labels = labels_for(pairs)
    alarm = np.zeros((T, M), bool)
    for t, m in pairs[::2]:
        alarm[t + 1, m] = True       # one day after the label: inside the window
    alarm[100 + 25, 0] = True        # far from any label: a false alarm
    metrics = alarm_metrics(alarm, scored, labels, test)
    hits = len(pairs[::2])
    assert metrics["alarms"] == hits + 1 and metrics["alarm_hits"] == hits
    assert metrics["labels_detected"] == hits and metrics["recall"] == pytest.approx(hits / len(pairs))
    assert metrics["first_alarm_offsets"]["1"] == hits
    assert metrics["lift"] > 5
    null = circular_shift_null(alarm, scored, labels, test, permutations=200)
    assert null["p_value"] < 0.01 and null["null_mean"] < 0.2


def test_calibration_on_quiet_days_excludes_label_neighbourhoods():
    T, M = 100, 1
    p = np.full((T, M), 0.5)
    p[50, 0] = 0.001  # next to a label: excluded
    p[10, 0] = 0.001  # quiet day: counted
    labels = labels_for([(52, 0)])
    out = calibration_on_quiet_days(p, labels, np.ones(T, bool))
    assert out["n"] == T - 15
    assert out["share_p_le_0.01"] == pytest.approx(1 / (T - 15))
