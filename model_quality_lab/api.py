from __future__ import annotations
from pathlib import Path
import json
import os
import time
import uuid
from urllib.parse import urlparse
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from .data import load_mind
from .engine import Lab
from .schema import Event, ExperimentRequest, PredictRequest, ModelSpec
from .telemetry import tracer

PROJECT = Path(__file__).resolve().parent.parent


def create_app(runtime: Path | None = None, dataset=None) -> FastAPI:
    runtime = runtime or Path(os.environ.get("MQL_RUNTIME", PROJECT / ".runtime"))
    if dataset is None and os.environ.get("MQL_MIND_DIR"):
        root = Path(os.environ["MQL_MIND_DIR"])
        dataset = load_mind(root / "train", root / "dev")
    lab = Lab(runtime, dataset)
    spec_path = PROJECT / "configs/news.json"
    spec = ModelSpec.model_validate_json(spec_path.read_text()) if spec_path.exists() else None
    app = FastAPI(title="Model Quality Lab", version="0.1.0", description="Local learning platform. Dataset replay is explicit; model execution and durable ingestion are real.")
    app.state.lab = lab

    @app.middleware("http")
    async def browser_boundary(request: Request, call_next):
        origin = request.headers.get("origin")
        if request.method not in ("GET", "HEAD", "OPTIONS") and origin:
            parsed = urlparse(origin)
            if parsed.netloc != request.headers.get("host"):
                return JSONResponse({"detail": "Cross-origin writes are disabled"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.get("/healthz")
    def health():
        return {"status": "ok", "dataset": lab.ds.name}

    @app.get("/api/state")
    def state():
        return {**lab.state(), "onboarding": spec.model_dump() if spec else None}

    @app.get("/api/preview")
    def preview(index: int = 0):
        return lab.preview(index)

    @app.post("/api/experiments")
    def experiment(body: ExperimentRequest):
        return lab.run(body.scenario)

    @app.post("/api/runs/{run_id}/labels")
    def labels(run_id: str):
        try:
            return lab.release_labels(run_id)
        except (KeyError, ValueError) as e:
            raise HTTPException(400, str(e)) from e

    @app.post("/api/events", status_code=202)
    def event(body: Event):
        if os.environ.get("MQL_KAFKA_BROKERS"):
            from .streaming import publish
            try:
                publish(body.model_dump())
            except RuntimeError as e:
                raise HTTPException(503, str(e)) from e
            lab.metrics.events.labels(body.kind, "broker_acknowledged").inc()
            return {"accepted": True, "projected": False, "event_id": body.event_id, "transport": "kafka"}
        try:
            accepted = lab.store.accept(body.event_id, body.kind, body.request_id, body.body.model_dump())
        except ValueError as e:
            raise HTTPException(409, str(e)) from e
        lab.metrics.events.labels(body.kind, "accepted" if accepted else "duplicate").inc()
        lab.metrics.pending.set(lab.store.stats()["pending"])
        return {"accepted": accepted, "projected": False, "event_id": body.event_id}

    @app.post("/api/worker/drain")
    def drain():
        n = lab.store.drain_batch(); lab.metrics.pending.set(lab.store.stats()["pending"])
        return {"projected": n, "pipeline": lab.store.stats()}

    @app.post("/api/predict")
    def predict(body: PredictRequest):
        imp = lab.ds.test[body.index % len(lab.ds.test)]
        with tracer().start_as_current_span("ranking.predict", attributes={"mql.model": body.model}) as span:
            started = time.perf_counter()
            features = lab.models.features.build(imp)
            scores = lab.models.generative.score(imp) if body.model == "semantic" else lab.models.predict(features, body.model)
            elapsed = time.perf_counter() - started
            lab.metrics.inference.labels(body.model).observe(elapsed)
            req = "live-" + uuid.uuid4().hex[:16]
            payload = {"model": body.model, "user": imp.user, "cohort": imp.cohort,
                       "candidate_ids": imp.candidates, "scores": scores.tolist(), "event_time": imp.time}
            if os.environ.get("MQL_KAFKA_BROKERS"):
                from .streaming import publish
                publish({"event_id": req + ":prediction", "request_id": req, "kind": "prediction", "body": payload})
            else:
                lab.store.accept(req + ":prediction", "prediction", req, payload)
            return {"request_id": req, "scores": scores.tolist(), "candidate_ids": imp.candidates,
                    "latency_ms": elapsed * 1000, "trace_id": format(span.get_span_context().trace_id, "032x"),
                    "provenance": "actual CPU inference on a replayed request; label not included in model input"}

    @app.get("/api/traces")
    def traces():
        file = runtime / "traces.jsonl"
        if not file.exists():
            return []
        return [json.loads(s) for s in file.read_text().splitlines()[-60:]]

    @app.get("/api/requirements")
    def requirements():
        return json.loads((PROJECT / "configs/requirements.json").read_text())

    @app.get("/api/adapters")
    def adapters():
        return {name: json.loads((runtime / filename).read_text()) if (runtime / filename).exists() else None
                for name, filename in (("vision", "vision-report.json"), ("slm", "slm-report.json"), ("resilience", "resilience-report.json"), ("benchmark", "benchmark.json"))}

    @app.get("/metrics")
    def metrics():
        lab.metrics.pending.set(lab.store.stats()["pending"])
        return Response(lab.metrics.render(), media_type="text/plain; version=0.0.4; charset=utf-8")

    @app.get("/")
    def index():
        return FileResponse(Path(__file__).parent / "static/index.html")

    app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
    if (PROJECT / "docs").exists():
        app.mount("/handbook", StaticFiles(directory=PROJECT / "docs", html=True), name="handbook")
    return app
