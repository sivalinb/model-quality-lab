# Run, observe and operate the lab

## Native application

Use Python 3.12 or 3.13 in a virtual environment. From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
mql suite
mql serve
```

Open http://127.0.0.1:7856. The app binds only to loopback. `/docs` is the generated OpenAPI interface; `/metrics` exposes Prometheus metrics. `/api/state` reports the dataset fingerprint, known scenarios, projections and run evidence. Runs persist in `.runtime/lab.sqlite3`; SDK traces persist in `.runtime/traces.jsonl`.

Mutating browser requests reject a different Origin. Schemas reject unknown fields, raw-text additions, arbitrary model aliases, duplicate candidate IDs and nonfinite scores. This is a trusted local developer lab; it has no enterprise identity provider, tenancy isolation or production RBAC. Do not expose it publicly as a service. The public website is a static replay of saved measurements and contains no backend or credentials.

## Native Grafana and Prometheus

If you already have official binaries, run:

```bash
python scripts/native_observability.py \
  --grafana-home /absolute/path/to/grafana \
  --prometheus-bin /absolute/path/to/prometheus \
  --prometheus-port 0
```

Grafana defaults to http://127.0.0.1:3016/d/model-quality-lab. Port zero chooses an available Prometheus port; `.runtime/observability/endpoints.json` records the actual addresses. An occupied requested port causes refusal, never replacement. The launcher creates separate data, configuration and log paths, and stops only its own child processes when interrupted. Dashboards are provisioned from version-controlled JSON. `python scripts/demo_traffic.py` produces real local API calls so inference histograms and envelope counters contain observations.

## Complete container stack

```bash
docker compose up --build -d
python scripts/integration_smoke.py --distributed
docker compose down
```

The stack includes API, Kafka, worker, ClickHouse, Prometheus, Grafana, OpenTelemetry Collector and Jaeger. Defaults: application 7856; Grafana 3016; Prometheus 9096; ClickHouse HTTP 8127; Jaeger 16696, all published to loopback. Broker ports are internal. Compose uses development credentials and a single broker; this configuration is a local integration exercise. Data volumes survive `down`; `down -v` intentionally removes only this Compose project's stored lab data.

`/api/events` in Kafka mode returns after broker acknowledgement. The worker projects and writes the analytical sink before committing offsets. The experiment runner's built-in scenarios retain their separate local inbox path. Use ClickHouse `FINAL` for logical event deduplication. Invalid schema messages are dead-lettered without copying raw rejected input. Offsets and explicit identities allow replay after a restart; there is no cross-sink exactly-once transaction.

## Public recommendation data

```bash
python scripts/download_mind.py
mql --runtime .runtime/mind-run --mind-dir .runtime/mind run --scenario healthy
mql --runtime .runtime/mind-run --mind-dir .runtime/mind run --scenario feature_skew
mql --runtime .runtime/mind-ui --mind-dir .runtime/mind serve --port 7857
```

The downloader uses the upstream Recommenders mirror, prints archive hashes and extracts only the expected TSV files. Source data remains local. Read the dataset's research terms linked at https://msnews.github.io/. For existing downloads, point `--mind-dir` at a folder containing `train/` and `dev/`, each with `news.tsv` and labeled `behaviors.tsv`.

## Actual local language-model inference

Use an existing Ollama installation and model. No secret is required for the default local server. `mql slm --model YOUR_MODEL --limit 6` performs actual calls. `--url` changes the local endpoint. Do not include credentials in URLs. The public evidence records the model, attempted cases, validity, matched quality, provider token counts and measured duration. Errors stay visible; a six-case run cannot authorize promotion.

## Failures and recovery

1. **Quality regresses, latency stays healthy:** inspect the paired feature/skew report and cohort comparison. Compare model and feature versions. Restore the correct feature path and verify quality using mature labels.
2. **Low label coverage:** check the request join key, label maturity, cohort-specific delivery and late-event policy. Do not turn missing outcomes into negative labels.
3. **Queue grows:** distinguish durable acceptance from projection. Check consumer logs, dead letters and lease age; restart the lab worker and verify identities rather than comparing raw log counts.
4. **Conflicting event identity:** reject changed content under the same event ID. Label corrections require a designed versioned correction workflow; this lab deliberately refuses silent overwrites.
5. **Analytical sink fails after local projection:** keep the Kafka offset uncommitted. Replayed envelopes deduplicate in local state and logically in ClickHouse.
6. **Blank Grafana panel:** execute its query directly against the provisioned Prometheus source. API prediction latency panels require actual prediction requests and at least two scrapes. Experimental quality gauges describe the latest completed run, not continuous live quality.

## Retention, access and governance

`retention_days` declares policy in the onboarding contract; automatic expiry is not implemented. For this local lab, stop producers, archive aggregate reports, back up state if needed, and remove the project's `.runtime` directory when discarding an experiment. A production implementation needs independently enforced TTLs for raw events, label joins, traces and audit evidence, plus deletion propagation and access review. Never publish raw source data, user-provided résumé files, credentials or `.runtime` databases.

## Validation commands

```bash
python -m pytest
python scripts/integration_smoke.py --in-process
python scripts/resilience.py
python scripts/benchmark.py --events 10000
python scripts/build_illustrations.py
python scripts/build_dashboard.py
python scripts/export_evidence.py
```

Benchmark output records event count, payload size, acceptance batch, projection transaction batch, host and Python version. Its throughput is a bounded local experiment with a warm filesystem; it excludes inference and network. Docker verification runs separately in CI. See [Validation](VALIDATION.md) for delivered results and the distinction between executed and proposed capabilities.
