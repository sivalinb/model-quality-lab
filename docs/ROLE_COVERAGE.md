# Role coverage and professional bridge

This project is shaped around the [LinkedIn Senior Staff Software Engineer, AI Infrastructure posting](https://jobs.smartrecruiters.com/LinkedIn3/744000144129949-senior-staff-software-engineer-ai-infrastructure). It targets its evaluation, monitoring, lifecycle and platform architecture themes. The complete implementation map is machine-readable in `configs/requirements.json` and visible in the app's **Role alignment** page.

| Area | Implemented evidence | Boundary |
|---|---|---|
| Evaluation | Frozen comparisons, cohort metrics, intervals, gates | Historical replay; no causal lift |
| Monitoring | Drift, missing features, paired skew, score changes | Diagnostic thresholds need calibration |
| Telemetry | Durable inbox, fenced workers, Kafka/ClickHouse adapter | Multi-zone availability is proposed |
| Lifecycle | Delayed outcomes, coverage and re-evaluation | Label correction is intentionally rejected |
| Productivity | Validated JSON contract, shared API/CLI/UI, CI | One ranking feature schema |
| Instrumentation | OTel SDK, OpenInference LLM spans, Grafana | No raw-prompt trace capture |
| Generative ranking | Semantic taxonomy tokens, autoregressive count model | No transformer training claim |
| Language models | Actual local calls and validity checks | Small smoke sample |
| Vision | Real digit classifier and pixel corruption | Illustrative holdout assumptions |
| Governance | Bounded schemas, pseudonyms, audit and retention procedure | Enterprise identity/TTL are exercises |
| Technical strategy | ADRs, SLO proposals, scale and rollout plan | Production adoption is separate evidence |
| Mentoring | Learning path and design-review workshop | Actual mentoring comes from career examples |

The résumé-to-project bridge is professional and deliberately general: observability roadmaps become model-monitoring standards; config-driven dashboard onboarding becomes a model contract; telemetry validation becomes model release evaluation; cardinality governance becomes bounded model telemetry; and cross-team consulting becomes an adoption and ownership design. No résumé, contact information or private production data is included in this repository.

Career duration, degree, architectural leadership and organizational influence remain professional qualifications. A personal lab can demonstrate technical work and learning; it cannot manufacture those credentials.

Suggested interview walkthrough: reproduce one serving defect, explain why latency was insufficient, inspect affected cohorts and confidence, trace delayed-label delivery, show crash recovery, and defend one distributed-systems tradeoff. Use real professional stories to explain decisions involving several teams.

Further primary reading: [LinkedIn model health assurance](https://www.linkedin.com/blog/engineering/analytics/model-health-assurance-at-linkedin), [OpenTelemetry Python instrumentation](https://opentelemetry.io/docs/languages/python/instrumentation/), [OpenInference specification](https://arize-ai.github.io/openinference/spec/), [MIND dataset](https://msnews.github.io/).
