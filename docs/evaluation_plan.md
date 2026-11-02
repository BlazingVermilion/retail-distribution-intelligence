# Evaluation plan

All targets below are acceptance criteria, not achieved benchmark results.

## Data engineering

- Repeating a load preserves row counts and exact monetary totals.
- Joins do not multiply facts; Unknown groups preserve reconciliation.
- Incomplete candidates cannot replace the current release.
- Recovery resumes/retries safely; source revisions are versioned.
- Record runtime, rows processed, query costs and bytes per snapshot on named hardware/configuration.

## AI automation

Create test cases for normal periods, missing data, inconsistent evidence, large negative adjustments and blocked metrics. Evaluate numeric claim correctness, evidence coverage, unsupported causal statements, appropriate abstention, schema validity, latency and token usage. Use deterministic template reports as a baseline. A manually reviewed reference set must be labeled as solo-authored, not an independent expert benchmark.

## Forecasting — later

Begin with seasonal-naive baselines and chronological rolling-origin evaluation. Choose aggregation only after checking history length and sparsity. Track MAE and suitable scaled/weighted metrics; define treatment of zero/negative targets. Never supply future realized drivers. Source publication lag and revisions affect what was known at each origin; current snapshots alone cannot perfectly reconstruct vintage data.

## Business impact

Do not claim revenue uplift or analyst time savings without a measured user study. A timed scripted demo measures demo execution, not organizational productivity.
