# Fix rehearsal evaluation

IncidentLab compares a single proposed fix with bounded experiments on isolated
copies of the current lab. The purpose is to test whether a measured plan can
resolve compound failures that a one-shot diagnosis leaves partially repaired.
This is an offline systems benchmark; it makes no claim about Mistral accuracy,
production incident resolution, or first-ever research novelty.

## Reproduce

```sh
docker compose --profile eval run --build --rm eval \
  python -m incidentlab.evaluation.rehearsal --split test \
  --output artifacts/rehearsal-test.json
```

For a local Python environment, use `uv run python -m
incidentlab.evaluation.rehearsal --split test`. `--split smoke` runs one seed per
scenario. The JSON artifact includes the complete manifest, its SHA-256,
dependency versions, timestamps, findings, traces, measured experiments,
selected actions, errors, and fresh verification responses. It is generated
under `artifacts/` and ignored by Git; preserve it when sharing a result.

## Frozen cases

The evaluator-owned manifest lives in `src/incidentlab/evaluation/rehearsal.py`.
Smoke uses seed 42; the regression split named `test` uses 11, 23, and 37.

| Group | Mechanisms | Test episodes |
| --- | --- | --- |
| Single faults | Inventory route, inventory readiness, client timeout, catalog path, checkout release | 15 |
| Compound faults | Route + release, catalog + inventory, timeout + release | 9 |
| Controls | Healthy checkout; unavailable diagnostic telemetry | 6 |
| Total | 10 known scenario families | 30 |

The three seeds exercise each known mechanism repeatedly. They are not 30
independent real incidents, and `test` does not mean unseen fault families or a
held-out scientific study. Expected action sets are checked against scenario
metadata to detect drift. Ground-truth action sets are used only for scoring;
the evaluator never substitutes them for a selected action.

## Protocol

1. Use separate lab instances for the two arms. Inject the same scenario and
   seed into each, generating initial real HTTP requests.
2. The baseline reads evidence, chooses at most one allowlisted action, and
   receives no retries. Capture its finding and tool traces.
3. Rehearsal snapshots the current application state. Measure a no-action
   control and candidate plans in disposable copies using three checkout
   requests per experiment. Search is limited to the five allowed actions and
   plans of at most two actions: at most 15 candidates plus the control.
4. Rehearsal selects a shortest successful measured plan when the control is
   failing and evidence is available. A healthy control requires no change;
   unavailable diagnostic telemetry requires abstention.
5. Apply only each arm's selected plan to that arm's source lab. Then issue
   five additional fresh checkout requests. Recovery requires all five HTTP
   responses to be 200. Save unsuccessful plans and errors as well as successes.

This comparison deliberately changes the available action and experiment
budget. It measures the benefit and cost of rehearsal over a one-shot workflow,
not whether two equally resourced agents differ in reasoning quality. A retrying
baseline, broader actions, more than two simultaneous faults, and ambiguous or
nonrecoverable faults would be useful next comparisons.

## Metrics

| Metric | Denominator and interpretation |
| --- | --- |
| Recovery rate | Verified recoveries / 24 actionable fault episodes |
| Single / compound recovery | Verified recoveries / 15 single or 9 compound episodes |
| Improvement | Rehearsal recovery minus baseline recovery, in percentage points |
| Control no-action rate | Completed runs with no action / 6 control episodes |
| Telemetry abstention | Completed runs with no action / 3 telemetry-gap episodes |
| Candidate experiments | Every saved nonempty action-plan experiment, including failures |
| Rehearsal probes | Recorded requests in control and candidate experiments |
| Episode latency | Injection, decision procedure, action execution, and final verification |

Errors stay in the quality denominators. A failed control arm does not count as
successful abstention. Both arms are attempted even if the other fails. Timing
medians include completed arms; total episode time includes failed attempts.
The report also records end-to-end evaluation wall time, including lab setup and
cleanup. Rehearsal has a larger compute and request budget, which must accompany
any recovery claim.

HTTP 200 on a small batch does not prove semantic correctness, long-term
reliability, absence of side effects, or production safety. Snapshot cloning is
implemented for this local HTTP/SQLite application. No production resources are
cloned or changed. Mistral performance requires a separate live model evaluation.

## Recorded result — 2026-10-17

IncidentLab 0.2.0 completed the Docker `test` split at 14:05:08–14:06:32 UTC.
All 30 episodes completed in both arms, with zero execution errors. The full run
took 84.51 seconds. Machine-readable metadata and aggregates are checked in as
[rehearsal-results.json](results/rehearsal-results.json).

| Measure | One-shot baseline | Fix rehearsal |
| --- | --- | --- |
| Verified recovery, all actionable faults | 15/24 (62.5%) | 24/24 (100%) |
| Verified recovery, single faults | 15/15 | 15/15 |
| Verified recovery, compound faults | 0/9 | 9/9 |
| No action on healthy or missing-telemetry controls | 6/6 | 6/6 |
| No action on missing-telemetry controls | 3/3 | 3/3 |
| Median complete episode time | 15.72 ms | 1,717.40 ms |
| Total time across all arms of this type | 10.26 s | 74.04 s |
| Model API calls | 0 | 0 |

Rehearsal improved recovery by **37.5 percentage points** across the 24 fault
episodes. The difference came from the nine compound-fault episodes: a single
fix left a second fault unresolved, while the selected two-action plans passed
five fresh verification requests after promotion. Both methods preserved all
six no-action decisions in the controls.

This improvement used a larger budget: **405 candidate experiments**, 30
no-action control experiments, and **1,305 rehearsal HTTP requests**, in addition
to injection and final verification traffic. Healthy episodes also tested the
candidate plans but recommended no change; missing-telemetry episodes ran only
the control and abstained. The result supports this finite, known-scenario
workflow comparison. It does not show superior equal-budget reasoning, Mistral
performance, production recovery rates, or reduced real incident resolution
time.

Environment: Python 3.11.17, Linux 6.12.54 linuxkit aarch64, glibc 2.41;
FastAPI 0.143.3, httpx 0.28.1, Pydantic 2.14.1. Dependencies are frozen in
`uv.lock`. Timings reflect this machine and run.

The generated full artifact, `artifacts/rehearsal-test.json`, is 613,427 bytes.
Preserve it with the summary when sharing the result. Its SHA-256 is:

```text
fc525a68d254f8a6db4b6501a22e628ab1b487722c4487d60f4b06e5686da463
```

Frozen manifest SHA-256:

```text
352eb3fce3d1888a3546c3196f2ea752ca4e32265b630f9a3427f3602d472cdd
```
