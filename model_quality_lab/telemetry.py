"""Actual OpenTelemetry spans; bounded Prometheus labels; optional OTLP export."""
from __future__ import annotations
from pathlib import Path
import json
import os
import threading
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult, BatchSpanProcessor
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest

_provider = None
_lock = threading.Lock()


class JsonlExporter(SpanExporter):
    def __init__(self, path: Path):
        self.path = path; self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()

    def export(self, spans):
        with self.lock, self.path.open("a") as f:
            for span in spans:
                f.write(json.dumps(json.loads(span.to_json()), separators=(",", ":")) + "\n")
        return SpanExportResult.SUCCESS

    def shutdown(self):
        pass


def configure(runtime: Path):
    global _provider
    with _lock:
        if _provider is None:
            _provider = TracerProvider(resource=Resource.create({"service.name": "model-quality-lab", "service.version": "0.1.0"}))
            _provider.add_span_processor(SimpleSpanProcessor(JsonlExporter(runtime / "traces.jsonl")))
            endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
            if endpoint:
                from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
                _provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint.rstrip("/") + "/v1/traces")))
    return _provider


def tracer():
    if _provider is None:
        # A no-op tracer is sufficient for unit tests that do not configure a lab.
        from opentelemetry import trace
        return trace.get_tracer("model_quality_lab")
    return _provider.get_tracer("model_quality_lab", "0.1.0")


class Metrics:
    def __init__(self):
        self.registry = CollectorRegistry()
        self.runs = Counter("mql_experiments_total", "Completed experiments", ["scenario", "decision"], registry=self.registry)
        self.ndcg = Gauge("mql_ndcg", "Latest joined-label ranking quality", ["model", "cohort"], registry=self.registry)
        self.coverage = Gauge("mql_label_coverage_ratio", "Latest experiment joined label fraction", registry=self.registry)
        self.skew = Gauge("mql_feature_skew_ratio", "Latest experiment training-serving mismatch", registry=self.registry)
        self.pending = Gauge("mql_inbox_pending", "Durably accepted events awaiting projection", registry=self.registry)
        self.inference = Histogram("mql_inference_seconds", "Actual API ranking computation duration", ["model"],
                                   buckets=(.0001, .0005, .001, .005, .01, .05, .1, .5, 1, 5), registry=self.registry)
        self.events = Counter("mql_events_total", "Accepted and duplicate API events", ["kind", "outcome"], registry=self.registry)

    def render(self) -> bytes:
        return generate_latest(self.registry)
