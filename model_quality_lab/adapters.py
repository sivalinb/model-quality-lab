"""Additional model families exercise the same lifecycle, with task-specific metrics."""
from pathlib import Path
import json
import time
import numpy as np
from sklearn.datasets import load_digits
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, log_loss, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from .telemetry import tracer
from .evaluation import ranking_metrics
from .models import OllamaRanker


def vision_experiment(output: Path) -> dict:
    """Actual CPU classifier on public hand-written digit images bundled by sklearn."""
    x, y = load_digits(return_X_y=True)
    xt, xe, yt, ye = train_test_split(x, y, test_size=.3, random_state=42, stratify=y)
    with tracer().start_as_current_span("vision.train_evaluate"):
        model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=500, random_state=42))
        t = time.perf_counter(); model.fit(xt, yt)
        p = model.predict_proba(xe)
        corrupted = xe.copy(); corrupted[:, 24:40] = 0
        cp = model.predict_proba(corrupted)
        correct, bad = p.argmax(axis=1) == ye, cp.argmax(axis=1) == ye
        rng = np.random.default_rng(42); indices = rng.integers(0, len(ye), (1000, len(ye)))
        delta = bad.astype(float) - correct.astype(float)
        lo, hi = np.quantile(delta[indices].mean(axis=1), [.025, .975])
        result = {"task": "vision-classification", "dataset": "sklearn digits (UCI optical handwritten digits)",
                  "provenance": "real public image samples; controlled pixel occlusion; CPU inference",
                  "train_samples": len(yt), "test_samples": len(ye), "split": "stratified seeded holdout; not temporal",
                  "baseline_accuracy": float(accuracy_score(ye, p.argmax(axis=1))),
                  "candidate_accuracy": float(accuracy_score(ye, cp.argmax(axis=1))),
                  "accuracy_delta_ci": [float(lo), float(hi)], "baseline_log_loss": float(log_loss(ye, p)),
                  "candidate_log_loss": float(log_loss(ye, cp)),
                  "confusion_matrix": confusion_matrix(ye, cp.argmax(axis=1)).tolist(),
                  "duration_seconds": time.perf_counter() - t,
                  "limitations": "Image holdout may share writers; per-image bootstrap is illustrative, not writer-independent evidence"}
    output.parent.mkdir(parents=True, exist_ok=True); output.write_text(json.dumps(result, indent=2))
    return result


def slm_experiment(lab, model: str, limit: int = 6, base_url: str = "http://127.0.0.1:11434") -> dict:
    ranker = OllamaRanker(model, base_url)
    cases = []
    for imp in lab.ds.test[:limit]:
        try:
            result = ranker.rank(imp, lab.ds)
            rank = {a: len(result["ranked_ids"]) - n for n, a in enumerate(result["ranked_ids"])}
            result["metrics"] = ranking_metrics(imp.labels, [rank[a] for a in imp.candidates], imp.candidates)
            result["valid"] = True
        except Exception as exc:
            result = {"valid": False, "error": str(exc)[:200], "metrics": None}
        # A frozen deterministic comparator is evaluated on exactly the same offered set.
        f = lab.models.features.build(imp)
        result["baseline_metrics"] = ranking_metrics(imp.labels, lab.models.predict(f).tolist(), imp.candidates)
        cases.append(result)
    valid = [c for c in cases if c["valid"] and c["metrics"]["eligible"]]
    result = {"task": "slm-ranking", "model": model, "attempted_cases": len(cases),
              "valid_output_rate": sum(c["valid"] for c in cases) / max(1, len(cases)),
              "ndcg_on_valid_cases": float(np.mean([c["metrics"]["ndcg"] for c in valid])) if valid else None,
              "baseline_ndcg_on_same_valid_cases": float(np.mean([c["baseline_metrics"]["ndcg"] for c in valid])) if valid else None,
              "decision": "INSUFFICIENT_EVIDENCE", "cases": cases,
              "limitations": "Small smoke sample; invalid outputs reported separately; local inference cost unmeasured"}
    (lab.runtime / "slm-report.json").write_text(json.dumps(result, indent=2))
    return result
