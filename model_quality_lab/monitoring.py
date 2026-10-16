"""Distribution monitoring is diagnostic; it does not prove model degradation."""
from __future__ import annotations
import numpy as np
from .data import FEATURES


def js_distance(reference: np.ndarray, observed: np.ndarray) -> dict:
    r = reference[np.isfinite(reference)]; o = observed[np.isfinite(observed)]
    if not len(r) or not len(o):
        return {"js_divergence": None, "reference": [], "observed": [], "edges": []}
    edges = np.unique(np.quantile(r, np.linspace(0, 1, 11)))
    if len(edges) < 3:
        center = float(np.median(r)); edges = np.array([-np.inf, center - 1e-6, center + 1e-6, np.inf])
    else:
        edges[0] = -np.inf; edges[-1] = np.inf
    p = np.histogram(r, bins=edges)[0].astype(float) + 1e-6
    q = np.histogram(o, bins=edges)[0].astype(float) + 1e-6
    p /= p.sum(); q /= q.sum(); m = (p + q) / 2
    js = .5 * (np.sum(p * np.log(p / m)) + np.sum(q * np.log(q / m)))
    return {"js_divergence": float(max(0, js)), "reference": p.tolist(), "observed": q.tolist(),
            "edges": [float(v) if np.isfinite(v) else ("-inf" if v < 0 else "inf") for v in edges]}


def monitor(reference: np.ndarray, offline: np.ndarray, served: np.ndarray,
            base_scores: np.ndarray, candidate_scores: np.ndarray, latencies: list[float]) -> dict:
    valid = np.isfinite(served)
    # NaN mismatches count as skew; isclose equal_nan would conceal a serving defect.
    different = ~np.isclose(offline, served, atol=1e-8, rtol=1e-6)
    return {"features": {name: {**js_distance(reference[:, j], served[:, j]),
                                 "missing_rate": float(1 - valid[:, j].mean()),
                                 "skew_rate": float(different[:, j].mean())}
                         for j, name in enumerate(FEATURES)},
            "skew_rate": float(np.any(different, axis=1).mean()),
            "missing_rate": float(1 - valid.mean()),
            "scores": js_distance(base_scores, candidate_scores),
            "latency_ms": {"p50": float(np.percentile(latencies, 50)),
                           "p95": float(np.percentile(latencies, 95)),
                           "p99": float(np.percentile(latencies, 99)),
                           "scope": "measured per-impression CPU prediction; excludes network and queue time"},
            "drift_threshold": .1, "drift_policy": "illustrative diagnostic JS threshold; never a quality verdict"}
