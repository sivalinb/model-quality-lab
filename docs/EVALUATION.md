# Evaluation and evidence

## Frozen task and splits

An impression is one offered candidate set with its recorded binary outcomes. It is never split into arbitrary train and test rows. Synthetic train, validation and test periods are strictly ordered. The MIND importer sorts complete training impressions by timestamp, creates an internal temporal validation boundary, retains a bounded recent training window, and evaluates on later official development impressions. The official dev subset is the lab's held-out evaluation, not MIND's hidden test benchmark. Candidate lists are preserved; unseen unoffered items are not labeled negative.

Training-only click counts feed popularity features. Past histories supplied with each impression feed topic, subtopic and title affinity. Evaluation targets never enter feature extraction. The manifest hashes article metadata and full split contents, including histories, candidate sets, labels and ordering. The model's random seed and policy are recorded. Validation is held out for future tuning; the initial model uses fixed hyperparameters and does not optimize against the test set.

## Metrics

For binary relevance, DCG@k is the sum of clicked-item gains divided by `log2(rank + 1)`; NDCG divides by the ideal candidate ordering's DCG. MRR uses the first clicked candidate in the complete ordering. Recall@10 is the fraction of clicked candidates retrieved in the first ten positions. Equal scores use lexicographic article identity as a deterministic tie-break, rather than an expectation over ties. Report this choice when comparing libraries.

Zero-positive impressions are ineligible for these ranking comparisons and counted separately. This conditioning is a limitation of the reported task; they should be evaluated by other operational or outcome metrics in a real product. Baseline and candidate share identical eligible groups. The mean gives equal weight to eligible impressions, not users.

## Uncertainty and release policy

The paired difference is candidate NDCG minus baseline NDCG. Bootstrap draws sample users with replacement and include each sampled user's full collection of eligible impressions. Sums and counts reproduce the impression-weighted population estimand. There are 1,000 default resamples, fixed seed 42, and percentile intervals. A Bonferroni adjustment covers the predeclared overall, new and returning comparisons. This is a learning implementation; alternatives and finite-sample behavior should be reviewed before production decisions.

Default minimums: 100 eligible overall impressions and 30 users; each protected slice needs 50 impressions and 20 users; joined-label coverage must reach 80%. The quality tolerance is 0.025 NDCG. If an interval crosses the non-inferiority boundary, approval is withheld. Missing features or paired skew above 1% independently block the release. This combines quality policy and input-contract policy; the report explains each reason.

Intervals are not valid for unlimited sequential peeking, adaptive slice selection or repeated test-set tuning. Time-correlated events, interference between users and nonstationarity need additional study. Missing labels may be nonrandom. Report label coverage by cohort and outcome delay distribution before treating complete cases as representative.

## Drift versus degradation

Jensen-Shannon divergence uses training-derived feature bins, with smoothed histograms and bounded tails. Prediction-score drift compares frozen baseline and candidate outputs on the replay. The illustrative threshold of 0.1 is diagnostic, not a calibrated universal alarm. The score-shift scenario proves that a distribution change can preserve every ranking metric. Calibration, selection bias and serving feature correctness require separate checks.

## Public data and live inference

MIND is a public research dataset under its own terms. Downloaded raw articles and behavior files are excluded from Git, Docker build context and release ZIP. Only aggregate measurements, source URLs and fingerprints are published. The upstream dataset mirror is taken from the maintained [Recommenders downloader](https://github.com/recommenders-team/recommenders/blob/main/recommenders/datasets/mind.py); original [MIND information and terms](https://msnews.github.io/).

Ollama smoke evaluations use actual model calls. A complete, unique permutation of offered IDs is required. Report validity over all attempted cases and ranking quality on the same valid cases for both models. This conditional comparison does not evaluate a production fallback policy. Small live samples are always labeled insufficient. Local compute cost is unmeasured, rather than reported as zero.

Digits classification uses real public images bundled with scikit-learn. Its metrics and split assumptions are task-specific. No laboratory result establishes production ML experience, business lift or large-fleet capacity.
