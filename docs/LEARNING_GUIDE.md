# Learn model quality through your observability experience

This project connects platform standards, config-driven monitoring, telemetry correctness, validation gates and cardinality governance to the model lifecycle. It adds model-specific measurement and statistical decisions to an existing infrastructure foundation.

![The model lifecycle](illustrations/architecture.png)

## 1. Run a healthy model

Run `mql suite`, then `mql serve`. Open http://127.0.0.1:7856. The default dataset is a seeded preference simulator: traffic and click outcomes are synthetic; model fitting, predictions, durable ingestion and evaluation are actual execution. The simulator is deliberately simple so you can reason about a planted fault.

Start in **Overview**. NDCG@10 rewards clicked articles placed near the top of the original candidate list. Inspect the number of eligible impressions, independent users, label coverage and dataset fingerprint. The learned click scorer, popularity heuristic and semantic-ID model are three different ranking approaches; the frozen learned model is the release baseline.

**Exercise:** Calculate DCG for relevance `[0, 1, 1]`, then divide by ideal DCG. Inspect `tests/test_evaluation.py` for the independent worked-value check. Explain why impressions without positive labels are excluded and counted rather than assigned a fictitious ranking score.

## 2. Reproduce a silent serving defect

![The silent feature fault](illustrations/experiment-flow.png)

Choose **A silent feature bug**. The experiment zeros topic affinity, subtopic affinity and title overlap for returning users. The baseline uses correct features on the exact same requests. The monitor compares both feature vectors, while the evaluator joins recorded outcomes to each prediction version.

**Exercise:** Before running, predict which cohort will regress. Compare the new-user and returning-user rows. Explain why a healthy p99 prediction duration cannot establish recommendation quality. Restore the healthy path and rerun to verify recovery.

Code to read: `data.py` → `models.py` → `engine.py` → `monitoring.py`.

## 3. Separate drift, skew and quality

Run **Drift without ranking loss**. Scores are transformed with `0.3 + 0.4 × score`. The mapping is strictly increasing, so ordering, NDCG and MRR stay unchanged while score distributions move. Calibration could change; this experiment does not claim calibration is preserved.

Run **An upstream data defect**. The monitor observes missing features before the scorer imputes zeros. Distribution change compares populations; paired skew compares two transforms for the same request. Neither substitutes for outcome-based quality measurement.

**Exercise:** Describe a benign population shift, a serving-code defect, and a label-confirmed quality regression. Explain why the JS threshold is diagnostic and illustrative rather than a universally calibrated alert threshold.

## 4. Earn a release decision

![Evidence-aware release gate](illustrations/release-gate.png)

Run **Labels arrive late**. Only 35% of impression outcomes enter the first join. The initial verdict withholds approval. Click **Deliver remaining labels and re-evaluate**; the same prediction versions gain complete outcome coverage and a new decision. Initial evidence is retained in the report.

The default policy permits a quality decrease of at most 0.025 NDCG. Resampling whole users preserves within-user dependence. Overall, new-user and returning-user comparisons use Bonferroni-adjusted intervals. A pass requires the lower interval endpoint to meet the non-inferiority boundary. A clear failure has its upper endpoint below that boundary. Ambiguous intervals stay insufficient.

**Exercise:** Raise the required coverage in `configs/news.json`. Run a sparse experiment. Discuss how selective missing labels could bias a fully observed subset, and why coverage alone does not solve that bias. Do not keep tuning thresholds against a test set and call the result an independent evaluation.

## 5. Recover the telemetry pipeline

![Durable event delivery](illustrations/delivery.png)

In **Event pipeline**, send one prediction. Acceptance persists an envelope; it is distinct from projection. Drain it, then inspect counts. A label can arrive before the prediction and still join later. Duplicate IDs with identical content are safe; reusing an ID with changed content is a conflict.

Run `python scripts/resilience.py`. A real child process claims an event and exits abruptly with code 77. After lease expiry, a fresh store processes the event. Verify one committed prediction, zero pending events and rejection of a repeated envelope.

**Exercise:** Kill a worker after a projection transaction begins. Explain transaction rollback, lease fencing, replay, dead letters and the difference between logical deduplication and distributed exactly-once delivery.

## 6. Try generative ranking

The semantic-ID baseline factors likelihood into topic, subtopic and item tokens. Taxonomy prefixes carry semantic meaning; the final article ID makes codes unique. Counts are learned only from training clicks and histories. Candidate-constrained decoding emits valid offered identities. This is a pedagogical autoregressive count model, not an LLM or a learned vector-quantization system.

With an existing Ollama service, run:

```bash
mql slm --model YOUR_INSTALLED_MODEL --url http://127.0.0.1:11434 --limit 6
```

Actual local inference returns a validated permutation of offered IDs. Targets are excluded from the prompt. Invalid or missing outputs are counted separately. OpenInference spans record model identity, measured duration and provider-reported token counts; raw prompts and outputs are not stored in traces. A small smoke sample always remains insufficient evidence for model promotion.

**Exercise:** Add article text that looks like an instruction. Confirm it cannot alter the allowed item universe. Measure failure rate and paired quality on the same valid cases. Define a fallback policy and score the full policy, including invalid responses, before comparing end-to-end systems.

## 7. Extend across model families

`mql vision` trains a real digit-image classifier. Pixel occlusion creates a controlled serving defect. Inspect accuracy, log loss and the confusion matrix. The seeded image holdout is not a temporal split and can share writers; its per-image interval is illustrative. Do not apply ranking metrics to classification outputs without defining the task.

The ranking scorer predicts clicks, but this project does not implement an ad auction or measure live CTR. MIND evaluations replay original offered sets; different rankings can change future user behavior, which recorded labels cannot establish.

## 8. Practice Senior Staff decisions

Read [Architecture](ARCHITECTURE.md), [Evaluation](EVALUATION.md), [Operations](OPERATIONS.md) and [Role coverage](ROLE_COVERAGE.md). Write a design review covering ownership, contracts, failure domains, backpressure, capacity, retention, change management and adoption. Ask another engineer to critique one decision and record the revision.

**Mentoring exercise:** Have a colleague onboard a configuration using only the README. Observe where they get stuck, improve the contract and document what changed. Actual organizational influence belongs in your professional examples; the lab provides concrete architecture and ML-evaluation material to discuss.
