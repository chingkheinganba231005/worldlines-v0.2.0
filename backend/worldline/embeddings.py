"""Learned representations, trained self-supervised on GDELT metadata only.

1. Event-type embeddings. Two CAMEO base codes are similar when the same news
   articles keep reporting them together. Positive pointwise mutual information
   of same-article co-occurrence (development year only), context-distribution
   smoothing 0.75, truncated SVD (Levy, Goldberg & Dagan 2015). Frozen thereafter.
   Uses: learned ground cost for optimal transport; a semantic-centroid channel.

2. Country "worldlines". Each month a country is described by whom it interacts
   with and how (partner x direction x QuadClass). PPMI + SVD gives a relational
   position; monthly positions are rotated onto a whole-period anchor by
   orthogonal Procrustes, so a country's path through the space - its worldline -
   reflects changing relations, not arbitrary SVD rotations.

Both are checked against external structure the training never saw (CAMEO
QuadClass and Goldstein scores; continents), reported in research/results.md.
"""
from __future__ import annotations

from collections import defaultdict

import numpy as np
from scipy.linalg import orthogonal_procrustes
from scipy.stats import spearmanr

from .reference import REFERENCE_DIR, ROOT_QUAD, ROOTS, actor_country, places

EMBEDDING_VERSION = "ppmi-svd-cooc-2023-d16"
DIM = 16


def ppmi(matrix: np.ndarray, context_alpha: float = 0.75) -> np.ndarray:
    total = matrix.sum()
    if total <= 0:
        raise ValueError("empty co-occurrence matrix")
    rows = matrix.sum(1, keepdims=True)
    cols = matrix.sum(0, keepdims=True) ** context_alpha
    with np.errstate(divide="ignore", invalid="ignore"):
        pmi = np.log(matrix * cols.sum() / (rows * cols))
    pmi[~np.isfinite(pmi)] = 0.0
    return np.maximum(pmi, 0.0)


def svd_embed(matrix: np.ndarray, dim: int = DIM) -> np.ndarray:
    u, s, _ = np.linalg.svd(matrix, full_matrices=False)
    vectors = u[:, :dim] * np.sqrt(s[:dim])
    # Fix SVD sign ambiguity deterministically: largest-magnitude loading positive.
    signs = np.sign(vectors[np.abs(vectors).argmax(0), np.arange(vectors.shape[1])])
    signs[signs == 0] = 1
    return vectors * signs


def normalize(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.maximum(norms, 1e-12)


# ----------------------------------------------------------------------------- event types
def event_type_embeddings(cooc_records: dict[str, dict], day_records: dict[str, dict], *, start: str, end: str,
                          min_count: int = 200) -> dict:
    counts: dict[str, float] = defaultdict(float)
    for day, record in day_records.items():
        if start <= day <= end and record.get("complete"):
            for code, n in record.get("base", {}).items():
                counts[code] += n
    codes = sorted(code for code, n in counts.items() if n >= min_count)
    index = {c: i for i, c in enumerate(codes)}
    matrix = np.zeros((len(codes), len(codes)))
    days = 0
    for day, record in cooc_records.items():
        if not (start <= day <= end):
            continue
        days += 1
        for key, n in record["pairs"].items():
            a, b = key.split("|")
            if a in index and b in index:
                matrix[index[a], index[b]] += n
                matrix[index[b], index[a]] += n
    vectors = normalize(svd_embed(ppmi(matrix)))
    return {"version": EMBEDDING_VERSION, "codes": codes, "vectors": vectors, "training": {"start": start, "end": end,
            "days": days, "pairs": float(matrix.sum() / 2)}, "counts": np.array([counts[c] for c in codes])}


def goldstein_lookup() -> dict[str, float]:
    out = {}
    for line in (REFERENCE_DIR / "CAMEO.goldsteinscale.txt").read_text(encoding="utf-8").splitlines()[1:]:
        if "\t" in line:
            code, value = line.split("\t")
            try:
                out[code.strip()] = float(value)
            except ValueError:
                continue
    return out


def check_event_embeddings(model: dict, k: int = 5, seed: int = 3) -> dict:
    """Does geometry learned from co-occurrence alone recover CAMEO's own semantics?"""
    codes, vectors = model["codes"], model["vectors"]
    quad = np.array([ROOT_QUAD[c[:2]] for c in codes])
    root = np.array([c[:2] for c in codes])
    similarity = vectors @ vectors.T
    np.fill_diagonal(similarity, -np.inf)
    neighbours = np.argsort(-similarity, axis=1)[:, :k]
    vote = np.array([np.bincount(quad[n], minlength=5).argmax() for n in neighbours])
    knn_quad = float(np.mean(vote == quad))
    same_root = float(np.mean(root[neighbours] == root[:, None]))
    majority = float(np.max(np.bincount(quad)) / len(quad))
    rng = np.random.default_rng(seed)
    shuffled = []
    for _ in range(200):
        perm = rng.permutation(len(codes))
        shuffled.append(np.mean(np.array([np.bincount(quad[perm][n], minlength=5).argmax() for n in neighbours]) == quad[perm]))
    gold = goldstein_lookup()
    have = [i for i, c in enumerate(codes) if c in gold]
    g = np.array([gold[codes[i]] for i in have])
    # Cross-validated linear readout of Goldstein from embeddings (5 folds).
    x = np.hstack([np.ones((len(have), 1)), vectors[have]])
    folds = np.arange(len(have)) % 5
    predicted = np.empty(len(have))
    for f in range(5):
        train, test = folds != f, folds == f
        beta = np.linalg.solve(x[train].T @ x[train] + 1e-2 * np.eye(x.shape[1]), x[train].T @ g[train])
        predicted[test] = x[test] @ beta
    rho = spearmanr(predicted, g).statistic
    return {"codes": len(codes), "knn_quadclass_accuracy": knn_quad, "majority_baseline": majority,
            "label_permutation_mean": float(np.mean(shuffled)), "label_permutation_p95": float(np.quantile(shuffled, 0.95)),
            "neighbours_same_root": same_root,
            "goldstein_cv_spearman": float(rho)}


def root_embeddings(model: dict) -> np.ndarray:
    """20 x DIM: count-weighted centroid of each root's base-code vectors (normalized)."""
    out = np.zeros((20, model["vectors"].shape[1]))
    for i, code in enumerate(model["codes"]):
        out[ROOTS.index(code[:2])] += model["counts"][i] * model["vectors"][i]
    return normalize(out)


def code_cost(model: dict, codes: list[str]) -> np.ndarray:
    """Ground cost 1 - cosine similarity between codes (missing codes use their root's centroid)."""
    roots = root_embeddings(model)
    lookup = {c: model["vectors"][i] for i, c in enumerate(model["codes"])}
    vectors = normalize(np.vstack([lookup.get(c, roots[ROOTS.index(c[:2])]) for c in codes]))
    cost = 1 - vectors @ vectors.T
    np.fill_diagonal(cost, 0.0)
    return np.maximum(cost, 0.0)


def project_2d(vectors: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    centered = vectors - vectors.mean(0)
    _, _, vt = np.linalg.svd(centered, full_matrices=False)
    return centered @ vt[:2].T, vt[:2]


# ----------------------------------------------------------------------------- countries
def relation_matrix(records: dict[str, dict], days: list[str], countries: list[str]) -> np.ndarray:
    """Country x context counts; context = (partner, direction, QuadClass); domestic dyads excluded."""
    index = {c: i for i, c in enumerate(countries)}
    C = len(countries)
    out = np.zeros((C, C * 8))
    for day in days:
        record = records.get(day)
        if not record or not record.get("complete"):
            continue
        for key, quads in record.get("dyad", {}).items():
            a, b = key.split(">")
            ia, ib = actor_country(a), actor_country(b)
            if ia is None or ib is None or ia == ib or ia not in index or ib not in index:
                continue
            i, j = index[ia], index[ib]
            for q in range(4):
                if quads[q]:
                    out[i, j * 8 + q] += quads[q]          # i acts on j
                    out[j, i * 8 + 4 + q] += quads[q]      # j receives from i
    return out


def country_worldlines(records: dict[str, dict], countries: list[str], months: list[str], *, window: int = 3,
                       min_events: int = 300) -> dict:
    by_month: dict[str, list[str]] = defaultdict(list)
    for day in records:
        by_month[day[:7]].append(day)
    matrices = {}
    for i, month in enumerate(months):
        days = [d for m in months[max(0, i - window + 1): i + 1] for d in by_month.get(m, [])]
        matrices[month] = relation_matrix(records, days, countries)
    anchor_matrix = sum(matrices.values())
    anchor_active = anchor_matrix.sum(1) >= min_events * len(months) / window
    anchor = np.zeros((len(countries), DIM))
    anchor[anchor_active] = normalize(svd_embed(ppmi(anchor_matrix[anchor_active][:, np.repeat(anchor_active, 8)])))
    positions: dict[str, np.ndarray] = {}
    active: dict[str, np.ndarray] = {}
    for month, matrix in matrices.items():
        rows = (matrix.sum(1) >= min_events) & anchor_active
        if rows.sum() < 20:
            continue
        vectors = np.zeros((len(countries), DIM))
        vectors[rows] = normalize(svd_embed(ppmi(matrix[rows][:, np.repeat(anchor_active, 8)])))
        rotation, _ = orthogonal_procrustes(vectors[rows], anchor[rows])
        aligned = np.zeros_like(vectors)
        aligned[rows] = normalize(vectors[rows] @ rotation)
        positions[month] = aligned
        active[month] = rows
    pooled = np.vstack([positions[m][active[m]] for m in positions])
    mean = pooled.mean(0)
    _, _, vt = np.linalg.svd(pooled - mean, full_matrices=False)
    plane = {m: (positions[m] - mean) @ vt[:2].T for m in positions}
    return {"months": list(positions), "positions": positions, "active": active, "plane": plane, "anchor": anchor,
            "anchor_active": anchor_active}


def check_worldlines(model: dict, countries: list[str], k: int = 5, seed: int = 5) -> dict:
    continent = np.array([places()[c].continent if c in places() else "?" for c in countries])
    month = model["months"][-1]
    rows = np.flatnonzero(model["active"][month])
    vectors = model["positions"][month][rows]
    similarity = vectors @ vectors.T
    np.fill_diagonal(similarity, -np.inf)
    neighbours = np.argsort(-similarity, axis=1)[:, :k]
    same = float(np.mean(continent[rows][neighbours] == continent[rows][:, None]))
    rng = np.random.default_rng(seed)
    null = [float(np.mean(continent[rows][rng.permutation(len(rows))][neighbours] == continent[rows][:, None])) for _ in range(200)]
    steps, shuffled = [], []
    months = model["months"]
    for a, b in zip(months, months[1:]):
        both = np.flatnonzero(model["active"][a] & model["active"][b])
        pa, pb = model["positions"][a][both], model["positions"][b][both]
        steps.extend(1 - np.sum(pa * pb, axis=1))
        shuffled.extend(1 - np.sum(pa * pb[rng.permutation(len(both))], axis=1))
    return {"month": month, "countries": int(len(rows)), "knn_same_continent": same,
            "continent_permutation_mean": float(np.mean(null)), "continent_permutation_p95": float(np.quantile(null, 0.95)),
            "median_monthly_step": float(np.median(steps)), "median_step_if_unaligned_identity": float(np.median(shuffled))}
