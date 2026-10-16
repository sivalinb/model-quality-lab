"""Experiment orchestration: train, serve, accept, join, evaluate, diagnose, gate."""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import json
import platform
import threading
import time
import uuid
import numpy as np
from .data import Dataset, FEATURES, synthetic
from .models import RankingModels
from .evaluation import ranking_metrics, release_gate, GatePolicy
from .monitoring import monitor
from .store import Store
from .telemetry import configure, tracer, Metrics

SCENARIOS = {
    "healthy": {"title": "Healthy release", "description": "The frozen model and serving features agree. Paired quality should pass.", "expected": "PASS"},
    "feature_skew": {"title": "A silent feature bug", "description": "Serving zeros returning users' topic, subtopic and title affinity. Latency can stay healthy.", "expected": "FAIL"},
    "score_shift": {"title": "Drift without ranking loss", "description": "A monotonic score transformation changes distributions but preserves every ordering.", "expected": "PASS"},
    "regression": {"title": "A bad model release", "description": "The candidate reverses scores. Labels are needed to establish quality loss.", "expected": "FAIL"},
    "missing_feature": {"title": "An upstream data defect", "description": "Affinity features become missing and are imputed at serving time; the monitor records the defect.", "expected": "FAIL"},
    "delayed_labels": {"title": "Labels arrive late", "description": "Only 35% of outcomes are available at the first evaluation; the gate must withhold a verdict.", "expected": "INSUFFICIENT_EVIDENCE"},
    "sparse_slice": {"title": "Too little evidence", "description": "Replay only 16 impressions. A perfect-looking score is insufficient evidence.", "expected": "INSUFFICIENT_EVIDENCE"},
    "semantic_ranker": {"title": "Autoregressive semantic IDs", "description": "Compare a trained taxonomy-token generative baseline with the frozen discriminative ranker.", "expected": "MEASURE"},
}


class Lab:
    def __init__(self, runtime: Path, dataset: Dataset | None = None):
        self.runtime = runtime; runtime.mkdir(parents=True, exist_ok=True)
        configure(runtime)
        self.store = Store(runtime / "lab.sqlite3")
        self.ds = dataset or synthetic()
        self.ds.validate()
        self.manifest = self.ds.manifest()
        from .schema import ModelSpec
        config = Path(__file__).resolve().parent.parent / "configs/news.json"
        self.spec = ModelSpec.model_validate_json(config.read_text())
        self.policy = GatePolicy(tolerance=self.spec.tolerance, min_label_coverage=self.spec.min_label_coverage,
                                 protected_slices=tuple(self.spec.protected_slices))
        with tracer().start_as_current_span("model.train"):
            self.models = RankingModels(self.ds)
        self.metrics = Metrics()
        self.lock = threading.Lock()
        self.reports_dir = runtime / "reports"; self.reports_dir.mkdir(exist_ok=True)

    def preview(self, index: int = 0) -> dict:
        i = self.ds.test[index % len(self.ds.test)]
        features = self.models.features.build(i)
        scores = self.models.predict(features)
        order = sorted(range(len(scores)), key=lambda j: (-scores[j], i.candidates[j]))
        return {"impression_id": i.id, "cohort": i.cohort,
                "history_topics": [self.ds.articles[a].topic for a in i.history[-6:]],
                "items": [{"id": i.candidates[j], "title": self.ds.articles[i.candidates[j]].title,
                           "topic": self.ds.articles[i.candidates[j]].topic, "score": float(scores[j]),
                           "clicked": bool(i.labels[j]), "semantic_id": self.models.generative.code(i.candidates[j])}
                          for j in order]}

    def _report_rows(self, run_id: str) -> list[dict]:
        grouped = {}
        for joined in self.store.joined(run_id + ":"):
            pred, label = joined["prediction"], joined["label"]
            # A label describes the complete recorded candidate set, not arbitrary unseen items.
            if set(pred["candidate_ids"]) != set(label["candidate_ids"]):
                raise ValueError("Label and prediction candidate sets differ")
            positives = set(label["clicked_ids"])
            metric = ranking_metrics([int(a in positives) for a in pred["candidate_ids"]], pred["scores"], pred["candidate_ids"])
            row = grouped.setdefault(joined["request_id"], {"user": pred["user"], "cohort": pred["cohort"]})
            row[pred["model"]] = metric
        return [r for r in grouped.values() if "baseline" in r and "candidate" in r]

    def run(self, scenario: str = "healthy", bootstrap: int = 1000) -> dict:
        if scenario not in SCENARIOS:
            raise ValueError("Unknown scenario")
        # Runs mutate the common replay inbox; serialize them to bound CPU and simplify UI semantics.
        with self.lock, tracer().start_as_current_span("experiment.run", attributes={"mql.scenario": scenario}) as span:
            started = time.perf_counter()
            run_id = uuid.uuid4().hex[:12]
            impressions = self.ds.test[:16] if scenario == "sparse_slice" else self.ds.test
            offline_all, served_all, baseline_all, candidate_all, latencies = [], [], [], [], []
            events, deferred = [], []
            for n, i in enumerate(impressions):
                x = self.models.features.build(i)
                served = x.copy()
                if scenario == "feature_skew" and i.cohort == "returning":
                    served[:, [0, 1, 4]] = 0
                if scenario == "missing_feature":
                    served[:, [0, 1, 4]] = np.nan
                baseline = self.models.predict(x)
                t0 = time.perf_counter()
                candidate = (self.models.generative.score(i) if scenario == "semantic_ranker"
                             else self.models.predict(np.nan_to_num(served)))
                if scenario == "score_shift":
                    candidate = .3 + .4 * candidate  # strictly monotonic: ranking metrics must be identical.
                elif scenario == "regression":
                    candidate = 1 - candidate
                latencies.append((time.perf_counter() - t0) * 1000)
                offline_all.append(x); served_all.append(served)
                baseline_all.append(baseline); candidate_all.append(candidate)
                req = f"{run_id}:{i.id}"
                for name, scores in (("baseline", baseline), ("candidate", candidate)):
                    payload = {"model": name, "user": i.user, "cohort": i.cohort,
                               "candidate_ids": i.candidates, "scores": scores.tolist(), "event_time": i.time}
                    events.append((req + ":" + name, "prediction", req, payload))
                label = (req + ":label", "label", req,
                         {"candidate_ids": i.candidates, "clicked_ids": [a for a, v in zip(i.candidates, i.labels) if v]})
                if scenario == "delayed_labels" and n % 20 >= 7:
                    deferred.append(label)
                else:
                    events.append(label)
            # Intentionally replay duplicate envelopes, proving event-ID deduplication on the real path.
            accepted = self.store.accept_many(events + events[:12])
            before = self.store.stats()
            self.store.drain_batch()
            rows = self._report_rows(run_id)
            mon = monitor(self.models.reference, np.concatenate(offline_all), np.concatenate(served_all),
                          np.concatenate(baseline_all), np.concatenate(candidate_all), latencies)
            with tracer().start_as_current_span("model.evaluate"):
                gate = release_gate(rows, len(impressions), mon["skew_rate"], mon["missing_rate"], policy=self.policy, bootstrap=bootstrap)
                popularity = []; semantic = []
                for i in impressions:
                    f = self.models.features.build(i)
                    popularity.append(ranking_metrics(i.labels, self.models.predict(f, "popularity").tolist(), i.candidates))
                    semantic.append(ranking_metrics(i.labels, self.models.generative.score(i).tolist(), i.candidates))
            trace_id = format(span.get_span_context().trace_id, "032x")
            report = {"id": run_id, "scenario": scenario, "title": SCENARIOS[scenario]["title"],
                      "created": datetime.now(timezone.utc).isoformat(), "trace_id": trace_id,
                      "dataset": self.manifest, "gate": gate, "monitoring": mon,
                      "model": {"baseline": "frozen logistic-v1", "candidate": "semantic-id-v1" if scenario == "semantic_ranker" else "logistic-v2/serving experiment",
                                "training_seconds": self.models.training_seconds, "features": list(FEATURES)},
                      "comparators": {"popularity_ndcg": float(np.mean([m["ndcg"] for m in popularity if m["eligible"]])),
                                      "semantic_ndcg": float(np.mean([m["ndcg"] for m in semantic if m["eligible"]]))},
                      "pipeline": {"accepted": accepted, "duplicate_envelopes": min(12, len(events)),
                                   "pending_before_processing": before["pending"], "processed": self.store.stats()["pending"] == 0,
                                   "joined_impressions": len(rows), "expected_impressions": len(impressions),
                                   "deferred_labels": len(deferred)},
                      "evidence": {"inference": "real CPU model execution", "transport": "real SQLite/WAL durable inbox",
                                   "traffic": "historical replay" if self.ds.name == "MIND-small" else "synthetic preference traffic",
                                   "quality": "recorded impression ranking; no causal CTR or business lift claim",
                                   "fault": "controlled serving perturbation" if scenario not in ("healthy", "semantic_ranker") else "none"},
                      "duration_seconds": time.perf_counter() - started,
                      "environment": {"python": platform.python_version(), "system": platform.platform()},
                      "example": self.preview(0)}
            if deferred:
                (self.runtime / f"deferred-{run_id}.json").write_text(json.dumps(deferred))
            self.store.save_run(report)
            (self.reports_dir / f"{run_id}.json").write_text(json.dumps(report, indent=2, allow_nan=False))
            self.metrics.runs.labels(scenario, gate["decision"]).inc()
            self.metrics.coverage.set(gate["label_coverage"]); self.metrics.skew.set(mon["skew_rate"])
            self.metrics.pending.set(self.store.stats()["pending"])
            for cohort, summary in {"overall": gate["overall"], **gate["slices"]}.items():
                for model in ("baseline", "candidate"):
                    if summary[f"{model}_ndcg"] is not None:
                        self.metrics.ndcg.labels(model, cohort).set(summary[f"{model}_ndcg"])
            self.store.audit("experiment.completed", {"run_id": run_id, "scenario": scenario, "decision": gate["decision"]})
            return report

    def release_labels(self, run_id: str) -> dict:
        if len(run_id) != 12 or not all(c in "0123456789abcdef" for c in run_id):
            raise ValueError("Invalid run identity")
        file = self.runtime / f"deferred-{run_id}.json"
        if not file.exists():
            raise ValueError("This run has no deferred labels")
        self.store.accept_many(json.loads(file.read_text())); self.store.drain_batch()
        reports = {r["id"]: r for r in self.store.runs(10000)}
        report = reports[run_id]
        rows = self._report_rows(run_id)
        report["initial_gate"] = report.get("initial_gate", report["gate"])
        report["initial_pipeline"] = report.get("initial_pipeline", report["pipeline"].copy())
        report["gate"] = release_gate(rows, report["pipeline"]["expected_impressions"],
                                      report["monitoring"]["skew_rate"], report["monitoring"]["missing_rate"], policy=self.policy)
        report["pipeline"].update({"joined_impressions": len(rows), "deferred_labels": 0})
        self.store.save_run(report)
        (self.reports_dir / f"{run_id}.json").write_text(json.dumps(report, indent=2))
        self.store.audit("labels.released", {"run_id": run_id, "decision": report["gate"]["decision"]})
        self.metrics.coverage.set(report["gate"]["label_coverage"])
        return report

    def state(self) -> dict:
        return {"dataset": self.manifest, "scenarios": SCENARIOS, "runs": self.store.runs(),
                "pipeline": self.store.stats(), "audit": self.store.audit_rows(),
                "features": list(FEATURES), "version": "0.1.0"}
