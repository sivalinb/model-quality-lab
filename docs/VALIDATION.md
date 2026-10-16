# Recorded validation

The repository preserves executed results in [evidence](evidence/). Screenshots are actual browser captures of the local application and Grafana. Workflow diagrams are labeled illustrations, generated from editable code.

## Executed locally

- 41 correctness tests passed, covering hand-calculated ranking metrics, paired clustering, gate policies, temporal leakage, event identity conflicts, late labels, concurrent consumers, stale-worker fencing, schema boundaries and the API.
- Eight model scenarios executed against 900 held-out synthetic impressions (16 for the sparse case). Healthy and monotonic-score-change runs passed; feature skew, missing features and reversed ranking failed; sparse and delayed-label runs withheld approval. The semantic-token baseline was measured independently of any expected verdict.
- The synthetic feature fault changed mean NDCG@10 from about 0.6372 to 0.4633. Traffic and click outcomes are simulated; model execution and statistics are real.
- A real child process exited with code 77 after claiming an accepted event. A fresh store recovered exactly one logical prediction; replaying its identical envelope did not add a second projection.
- A 10,000-event WAL benchmark recorded acceptance and projection duration, explicit batch sizes and host scope. Its rates exclude model inference, network and production replication.
- Real Ollama inference ran six ranking cases using `investigator-qwen3:4b`. Four returned valid complete permutations; two failed validation. NDCG on those four valid cases was approximately 0.7827 versus 0.5723 for the frozen comparator on the same cases. This conditional, tiny sample remains insufficient evidence; it is not an overall superiority claim.
- A real digit classifier evaluated 540 held-out images: clean accuracy approximately 98.15%; controlled pixel occlusion approximately 50.74%. Holdout and writer-dependence limits are recorded.
- MIND-small was downloaded from the maintained upstream mirror. Actual training used 8,000 temporally selected impressions, with 1,600 internal validation and 1,800 later evaluation impressions. Aggregate public-data reports record the fingerprint, measured quality, serving perturbation and cohort evidence. Raw dataset files are not published.
- Native Prometheus/Grafana and the live browser workflow are checked separately. The container integration workflow verifies the Kafka/ClickHouse/OTLP path in CI; its current Actions result is authoritative.

## Evidence boundaries

Public walkthroughs load recorded results; the hosted website does not run a model or accept operational writes. Synthetic, historical-public-data, actual local-model and proposed architecture evidence are labeled separately. None of these bounded results demonstrates production capacity, multi-zone availability, causal business improvement or organizational adoption.

Enterprise authentication, automatic retention enforcement, label-correction semantics, learned semantic quantization and transformer training are documented follow-on exercises. The implemented code does not claim those capabilities.
