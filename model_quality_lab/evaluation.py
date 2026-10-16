"""Paired ranking evaluation, user-cluster uncertainty, and evidence-aware gates."""
from __future__ import annotations

from dataclasses import dataclass, asdict
import math
import numpy as np


def ranking_metrics(labels: list[int], scores: list[float], ids: list[str], k: int = 10) -> dict:
    if len(labels) != len(scores) or len(ids) != len(scores) or len(set(ids)) != len(ids):
        raise ValueError("Labels, scores, and unique candidate IDs must align")
    if not scores or not np.isfinite(scores).all() or not set(labels) <= {0, 1}:
        raise ValueError("Scores must be finite and labels binary")
    positives = sum(labels)
    if not positives:
        return {"eligible": False, "ndcg": None, "mrr": None, "recall": None}
    order = sorted(range(len(ids)), key=lambda j: (-scores[j], ids[j]))
    selected = [labels[j] for j in order[:k]]
    dcg = sum(v / math.log2(r + 2) for r, v in enumerate(selected))
    ideal = sum(1 / math.log2(r + 2) for r in range(min(k, positives)))
    mrr = next((1 / (r + 1) for r, j in enumerate(order) if labels[j]), 0.0)
    return {"eligible": True, "ndcg": dcg / ideal, "mrr": mrr,
            "recall": sum(selected) / positives}


def paired_summary(rows: list[dict], alpha: float = .05, bootstrap: int = 1000, seed: int = 42) -> dict:
    eligible = [r for r in rows if r["baseline"]["eligible"] and r["candidate"]["eligible"]]
    if not eligible:
        return {"impressions": 0, "users": 0, "baseline_ndcg": None, "candidate_ndcg": None,
                "delta": None, "ci": None, "baseline_mrr": None, "candidate_mrr": None,
                "baseline_recall": None, "candidate_recall": None, "excluded_zero_positive": len(rows)}
    groups = {}
    for r in eligible:
        groups.setdefault(r["user"], []).append(r["candidate"]["ndcg"] - r["baseline"]["ndcg"])
    sums = np.array([sum(v) for v in groups.values()])
    counts = np.array([len(v) for v in groups.values()])
    rng = np.random.default_rng(seed)
    choices = rng.integers(0, len(groups), size=(bootstrap, len(groups)))
    draws = sums[choices].sum(axis=1) / counts[choices].sum(axis=1)
    lo, hi = np.quantile(draws, [alpha / 2, 1 - alpha / 2])
    mean = lambda model, metric: float(np.mean([r[model][metric] for r in eligible]))
    return {"impressions": len(eligible), "users": len(groups),
            "baseline_ndcg": mean("baseline", "ndcg"), "candidate_ndcg": mean("candidate", "ndcg"),
            "baseline_mrr": mean("baseline", "mrr"), "candidate_mrr": mean("candidate", "mrr"),
            "baseline_recall": mean("baseline", "recall"), "candidate_recall": mean("candidate", "recall"),
            "delta": float(sums.sum() / counts.sum()), "ci": [float(lo), float(hi)],
            "confidence": 1 - alpha, "bootstrap_resamples": bootstrap,
            "excluded_zero_positive": len(rows) - len(eligible)}


@dataclass(frozen=True)
class GatePolicy:
    tolerance: float = .025
    min_impressions: int = 100
    min_users: int = 30
    min_slice_impressions: int = 50
    min_slice_users: int = 20
    min_label_coverage: float = .8
    max_skew_rate: float = .01
    max_missing_rate: float = .01
    protected_slices: tuple[str, ...] = ("new", "returning")
    alpha: float = .05


def release_gate(rows: list[dict], expected_impressions: int, skew: float = 0,
                 missing: float = 0, policy: GatePolicy = GatePolicy(), bootstrap: int = 1000) -> dict:
    # Bonferroni family: overall plus each predeclared protected slice.
    alpha = policy.alpha / (1 + len(policy.protected_slices))
    overall = paired_summary(rows, alpha, bootstrap)
    slices = {s: paired_summary([r for r in rows if r["cohort"] == s], alpha, bootstrap)
              for s in policy.protected_slices}
    coverage = len(rows) / max(1, expected_impressions)
    reasons = []
    insufficient = []
    if coverage < policy.min_label_coverage:
        insufficient.append(f"Only {coverage:.1%} of expected impressions have joined labels")
    if overall["impressions"] < policy.min_impressions or overall["users"] < policy.min_users:
        insufficient.append("Overall paired sample is below the impression/user minimum")
    for name, summary in slices.items():
        if summary["impressions"] < policy.min_slice_impressions or summary["users"] < policy.min_slice_users:
            insufficient.append(f"Protected slice {name} has insufficient independent users/impressions")
    if skew > policy.max_skew_rate:
        reasons.append(f"Training-serving skew {skew:.1%} exceeds {policy.max_skew_rate:.1%}")
    if missing > policy.max_missing_rate:
        reasons.append(f"Missing-feature rate {missing:.1%} exceeds {policy.max_missing_rate:.1%}")
    if not insufficient:
        for name, summary in {"overall": overall, **slices}.items():
            if summary["ci"][1] < -policy.tolerance:
                reasons.append(f"{name}: quality regression exceeds the {policy.tolerance:.3f} NDCG tolerance")
            elif summary["ci"][0] < -policy.tolerance:
                insufficient.append(f"{name}: confidence interval crosses the non-inferiority boundary")
    if reasons:
        decision = "FAIL"
    elif insufficient:
        decision = "INSUFFICIENT_EVIDENCE"
    else:
        decision = "PASS"
        reasons.append("All declared quality slices meet the non-inferiority policy and data checks")
    return {"decision": decision, "reasons": reasons + insufficient, "overall": overall, "slices": slices,
            "label_coverage": coverage, "policy": asdict(policy),
            "method": "paired user-cluster percentile bootstrap; impression-weighted mean; Bonferroni family",
            "comparison_scope": "historical candidate sets; not a causal online experiment"}
