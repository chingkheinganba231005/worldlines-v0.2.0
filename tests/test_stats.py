import math

import numpy as np
import pytest

from worldline import stats


def test_probability_rejects_invalid_distributions():
    for bad in ([1.0], [0, 0], [1, -1], [1, float("nan")], [[1, 2], [3, 4]]):
        with pytest.raises(ValueError):
            stats.probability(bad)
    assert np.allclose(stats.probability([1, 3]), [0.25, 0.75])


def test_jsd_properties():
    rng = np.random.default_rng(0)
    p, q = rng.dirichlet(np.ones(8)), rng.dirichlet(np.ones(8))
    assert stats.jsd(p, p) == pytest.approx(0.0, abs=1e-12)
    assert stats.jsd(p, q) == pytest.approx(stats.jsd(q, p))
    assert 0 < stats.jsd(p, q) <= math.log(2)
    assert stats.jsd([1, 0], [0, 1]) == pytest.approx(math.log(2))
    assert stats.js_contributions(p, q).sum() == pytest.approx(stats.jsd(p, q))


def test_transport_matches_one_dimensional_closed_form():
    rng = np.random.default_rng(1)
    p, q = rng.dirichlet(np.ones(6)), rng.dirichlet(np.ones(6))
    cost = np.abs(np.subtract.outer(np.arange(6), np.arange(6))).astype(float)
    closed_form = np.abs(np.cumsum(p) - np.cumsum(q))[:-1].sum()
    assert stats.transport(p, q, cost) == pytest.approx(closed_form, abs=1e-9)
    assert stats.transport(p, p, cost) == 0.0


def test_ilr_round_trip():
    p = np.array([0.1, 0.2, 0.3, 0.4])
    assert np.allclose(stats.inverse_ilr(stats.ilr(p)), p)
    assert np.allclose(stats.ilr_matrix(p[None, :])[0], stats.ilr(p))
    with pytest.raises(ValueError):
        stats.ilr([0.5, 0.5, 0.0])


def test_ridge_leaves_unpenalized_columns_free():
    rng = np.random.default_rng(2)
    x = np.hstack([np.ones((200, 1)), rng.normal(size=(200, 3))])
    y = 5.0 + x[:, 1:] @ np.array([1.0, -2.0, 0.5]) + rng.normal(scale=0.1, size=200)
    assert np.allclose(stats.fit_ridge(x, y, 0.0), np.linalg.lstsq(x, y, rcond=None)[0])
    heavy = stats.fit_ridge(x, y, 1e9)
    assert heavy[0] == pytest.approx(y.mean(), abs=0.05)  # intercept not shrunk
    assert np.all(np.abs(heavy[1:]) < 1e-3)


def test_weekday_dummies_are_effect_coded():
    d = stats.weekday_dummies(range(7))
    assert d.shape == (7, 6)
    assert np.allclose(d[6], -1.0)
    assert np.allclose(d.sum(0), 0.0)


def test_conformal_pvalue_formula_and_validity():
    assert stats.conformal_pvalue(5.0, [1, 2, 3, 4]) == pytest.approx(1 / 5)
    assert stats.conformal_pvalue(0.0, [1, 2, 3, 4]) == pytest.approx(1.0)
    assert stats.conformal_pvalue(float("nan"), [1, 2]) is None
    rng = np.random.default_rng(3)
    calibration = rng.normal(size=999)
    p = np.array([stats.conformal_pvalue(s, calibration) for s in rng.normal(size=4000)])
    for alpha in (0.01, 0.05, 0.2):
        assert np.mean(p <= alpha) <= alpha + 0.015


def test_gpd_pwm_recovers_parameters():
    rng = np.random.default_rng(4)
    xi, sigma = 0.2, 2.0
    u = rng.uniform(size=20000)
    sample = np.sort(sigma / xi * ((1 - u) ** -xi - 1))
    fit_xi, fit_sigma = stats.gpd_pwm(sample)
    assert fit_xi == pytest.approx(xi, abs=0.05)
    assert fit_sigma == pytest.approx(sigma, rel=0.05)
    assert stats.gpd_pwm(np.array([1.0, 2.0])) is None


def test_tail_pvalue_extrapolates_beyond_the_calibration_window():
    rng = np.random.default_rng(5)
    prior = rng.normal(size=365)
    body = stats.tail_pvalue(0.0, prior)
    assert body == pytest.approx(stats.conformal_pvalue(0.0, prior))
    beyond = stats.tail_pvalue(prior.max() + 2.0, prior)
    assert beyond < 1 / 366  # a plain rank could never go below 1/(n+1)
    scores = np.linspace(1.5, 6, 20)
    values = [stats.tail_pvalue(s, prior) for s in scores]
    assert all(a >= b for a, b in zip(values, values[1:]))
    assert stats.tail_pvalue(1e9, prior) >= 1e-6
    assert stats.tail_pvalue(1.0, []) is None


def test_tail_pvalue_is_calibrated_on_iid_scores():
    rng = np.random.default_rng(6)
    hits = {0.05: 0, 0.01: 0}
    trials = 3000
    for _ in range(trials):
        prior = rng.standard_t(5, size=365)
        p = stats.tail_pvalue(rng.standard_t(5), prior)
        for alpha in hits:
            hits[alpha] += p <= alpha
    assert hits[0.05] / trials == pytest.approx(0.05, abs=0.015)
    assert hits[0.01] / trials == pytest.approx(0.01, abs=0.007)


def test_cauchy_combination():
    assert stats.cauchy_combination([0.3]) == pytest.approx(0.3)
    assert stats.cauchy_combination([0.02, 0.02, 0.02]) == pytest.approx(0.02)
    assert stats.cauchy_combination([None, 0.4, None]) == pytest.approx(0.4)
    assert stats.cauchy_combination([None]) is None
    tiny = stats.cauchy_combination([1e-14, 0.9])
    assert 0 < tiny < 1e-13
    # Weight 1 on a small p and 0 on a large one returns the small one.
    assert stats.cauchy_combination([0.01, 0.9], weights=[1.0, 0.0]) == pytest.approx(0.01)
    # Valid under independence: P(p <= alpha) close to alpha.
    rng = np.random.default_rng(7)
    combined = np.array([stats.cauchy_combination(rng.uniform(size=3)) for _ in range(20000)])
    assert np.mean(combined <= 0.05) == pytest.approx(0.05, abs=0.01)


def test_benjamini_hochberg():
    p = {"a": 0.001, "b": 0.008, "c": 0.039, "d": 0.041, "e": 0.042, "f": 0.06, "g": 0.074, "h": 0.205}
    assert stats.benjamini_hochberg(p, 0.05) == {"a", "b"}
    # Step-up: rank 3 alone fails (0.039 > 0.026) but rank 5 passes (0.042 <= 0.044), so ranks 1-5 are rejected.
    assert stats.benjamini_hochberg(p, 0.07) == {"a", "b", "c", "d", "e"}
    assert stats.benjamini_hochberg({}, 0.1) == set()


def test_display_transforms():
    assert stats.logit_pvalue_to_unusualness(0.01) == pytest.approx(2.0)
    assert stats.logit_pvalue_to_unusualness(0.0) == pytest.approx(6.0)
    assert stats.logit_pvalue_to_unusualness(None) is None
    assert stats.percentile_of(3, [1, 2, 3, 4]) == pytest.approx(62.5)
    assert stats.robust_z(10, [1, 2, 3, 4, 5]) > 3
