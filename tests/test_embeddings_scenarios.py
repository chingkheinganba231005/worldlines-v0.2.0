import numpy as np
import pytest

from worldline import embeddings as emb
from worldline import scenarios as sc


# ----------------------------------------------------------------------------- embeddings
def test_ppmi_is_zero_under_independence_and_nonnegative():
    rng = np.random.default_rng(0)
    independent = np.outer(rng.uniform(1, 5, 6), rng.uniform(1, 5, 6))
    assert np.allclose(emb.ppmi(independent, context_alpha=1.0), 0.0, atol=1e-12)
    assert np.all(emb.ppmi(rng.poisson(5, (6, 6)).astype(float)) >= 0)
    with pytest.raises(ValueError):
        emb.ppmi(np.zeros((3, 3)))


def test_svd_signs_are_deterministic():
    rng = np.random.default_rng(1)
    m = rng.uniform(size=(10, 10))
    m = m + m.T
    v = emb.svd_embed(m, dim=4)
    columns = np.arange(4)
    assert np.all(v[np.abs(v).argmax(0), columns] > 0)
    assert np.allclose(emb.svd_embed(m, dim=4), v)


@pytest.fixture(scope="module")
def model(synthetic):
    records, cooc = synthetic
    return emb.event_type_embeddings(cooc, records, start="2023-01-01", end="2023-12-31")


def test_event_embeddings_recover_cooccurrence_structure(model):
    """Synthetic articles mix codes within three groups far more often than across them."""
    group = lambda code: 0 if int(code[:2]) <= 5 else 2 if int(code[:2]) >= 15 else 1  # noqa: E731
    vectors = model["vectors"]
    assert vectors.shape == (20, emb.DIM) and np.allclose(np.linalg.norm(vectors, axis=1), 1.0)
    similarity = vectors @ vectors.T
    np.fill_diagonal(similarity, -np.inf)
    nearest = similarity.argmax(1)
    agreement = np.mean([group(model["codes"][i]) == group(model["codes"][j]) for i, j in enumerate(nearest)])
    assert agreement >= 0.9
    assert model["training"]["days"] == 365


def test_learned_ground_cost(model):
    cost = emb.code_cost(model, ["010", "020", "190", "195"])  # 195 is unseen: falls back to its root's centroid
    assert cost.shape == (4, 4) and np.allclose(cost, cost.T) and np.allclose(np.diag(cost), 0)
    assert np.all((cost >= 0) & (cost <= 2))
    assert cost[0, 1] < cost[0, 2]  # two verbal-cooperation codes are closer than cooperation and force
    assert cost[2, 3] == pytest.approx(0.0, abs=1e-9)


def test_country_worldlines_are_aligned_over_time(synthetic):
    records, _ = synthetic
    countries = sorted({"USA", "GBR", "IND", "RUS", "UKR", "CHN", "ISR", "FRA", "DEU", "NGA", "SDN", "BRA", "JPN", "KOR",
                        "TUR", "IRN", "EGY", "PAK", "MEX", "ZAF", "AUS", "CAN", "ITA", "ESP"})
    months = sorted({d[:7] for d in records})
    model = emb.country_worldlines(records, countries, months)
    check = emb.check_worldlines(model, countries)
    assert len(model["months"]) >= 10
    # Procrustes alignment: a stable world barely moves month to month, unlike an unaligned comparison.
    assert check["median_monthly_step"] < 0.1 * check["median_step_if_unaligned_identity"]


# ----------------------------------------------------------------------------- scenarios
def test_moving_average_coefficients_of_a_var1():
    A = np.array([[[0.5, 0.2], [0.0, 0.3]]])
    phi = sc.ma_coefficients(A, 5)
    for h in range(6):
        assert np.allclose(phi[h], np.linalg.matrix_power(A[0], h))


def test_generalized_irf_and_fevd():
    A = np.array([[[0.5, 0.0], [0.4, 0.2]]])  # variable 0 drives variable 1, not the reverse
    phi = sc.ma_coefficients(A, 10)
    sigma = np.diag([1.0, 2.0])
    g = sc.girf(phi, sigma)
    assert g.shape == (2, 11, 2)
    assert g[0, 0, 0] == pytest.approx(1.0) and g[0, 1, 1] == pytest.approx(0.4)  # out[shock, horizon, response]
    assert np.allclose(g[1, :, 0], 0.0)
    theta = sc.gfevd(phi, sigma, 10)
    assert np.allclose(theta.sum(1), 1.0)
    conn = sc.connectedness(theta)
    assert 0 <= conn["total"] <= 100
    assert conn["net"][0] > 0 > conn["net"][1]  # the driver is a net transmitter


def test_ridge_fit_matches_least_squares_without_penalty():
    rng = np.random.default_rng(2)
    X = np.hstack([np.ones((300, 1)), rng.normal(size=(300, 4)) * [1, 5, 0.1, 2] + [0, 3, 0, -1]])
    Y = X @ rng.normal(size=(5, 2)) + rng.normal(scale=0.1, size=(300, 2))
    assert np.allclose(sc.ridge_fit(X, Y, 0.0, free=1), np.linalg.lstsq(X, Y, rcond=None)[0], atol=1e-8)


def test_minnesota_recovers_a_simulated_spillover():
    rng = np.random.default_rng(3)
    T, n, lags = 1500, 3, 2
    x = np.zeros((T, n))
    for t in range(1, T):
        x[t, 0] = 0.6 * x[t - 1, 0] + rng.normal()
        x[t, 1] = 0.3 * x[t - 1, 1] + 0.5 * x[t - 1, 0] + rng.normal()
        x[t, 2] = 0.4 * x[t - 1, 2] + rng.normal()
    world = np.full(T, 1000.0)
    weekdays = np.arange(T) % 7
    clean = np.ones(T, bool)
    rows, X, free = sc.design(x, world, weekdays, clean, lags)
    beta = sc.minnesota_fit(X, x[rows], free, n, lags, lam=1.0, kappa=1.0)
    A = sc.lag_matrices(beta, free, n, lags)
    assert A[0][1, 0] == pytest.approx(0.5, abs=0.06) and A[0][0, 0] == pytest.approx(0.6, abs=0.06)
    assert abs(A[0][0, 1]) < 0.06 and abs(A[0][2, 0]) < 0.06
    shut = sc.lag_matrices(sc.minnesota_fit(X, x[rows], free, n, lags, lam=1.0, kappa=1e9), free, n, lags)
    assert abs(shut[0][1, 0]) < 1e-3  # kappa -> infinity switches cross-country dynamics off


def test_design_skips_windows_with_unclean_days():
    T = 30
    clean = np.ones(T, bool)
    clean[10] = False
    rows, X, free = sc.design(np.zeros((T, 2)), np.ones(T), np.arange(T) % 7, clean, lags=3)
    assert not any(10 <= r <= 13 for r in rows) and rows[0] == 3
    assert X.shape == (len(rows), free + 6) and free == 8
