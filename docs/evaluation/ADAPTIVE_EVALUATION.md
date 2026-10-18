# Adaptive experiment selection: recorded offline comparison

Run date: **2026-10-17**. This measures deterministic offline policies. No Mistral
model was called and no model reasoning score is reported.

## Protocol

Thirty cases repeat ten known scenarios at seeds 11, 23, and 37: 15 single-fault
episodes, nine compound-fault episodes, three healthy controls, and three
missing-telemetry controls. Each strategy gets a fresh independent HTTP/SQLite
lab, a no-change control, a ceiling of four candidate experiments, up to two
actions per plan, and three requests per experiment. Every candidate starts
from the original snapshot. A selected plan is applied and checked with five
fresh requests; recovery requires all five to return HTTP 200.

The adaptive policy maps observed error signatures to actions, retaining the
earlier action when a trial exposes another fault. The fixed-order comparator
tries route, dependency, timeout, and catalog fixes in that order and stops on
success or budget exhaustion. Its fifth single action (rollback) and all pairs
fall outside the four-candidate ceiling. This is a deliberately simple search
baseline, so its failures must not be presented as a competitive LLM or engineer
benchmark. Both policies stop early on success and abstain on the controls.

## Recorded results

| Measure | Offline adaptive policy | Fixed-order search |
| --- | ---: | ---: |
| Verified recovery, fault episodes | 24/24 (100%) | 12/24 (50%) |
| Single faults | 15/15 | 12/15 |
| Compound faults | 9/9 | 0/9 |
| Controls with no action | 6/6 | 6/6 |
| Candidate experiments | 33 | 78 |
| No-change control experiments | 30 | 30 |
| Recorded experiment requests | 189 | 324 |
| Final verification requests | 150 | 150 |
| Median complete episode | 369.01 ms | 500.55 ms |
| Execution errors | 0 | 0 |
| Model API calls | 0 | 0 |

Timing includes fresh lab construction, injection, selection, active-lab
application/verification, and cleanup. Request counts exclude injection and
diagnostic evidence traffic. The same candidate ceiling does not imply equal
compute or equal candidates actually consumed. Timings describe this local
Docker run, not production incident duration or a controlled latency study.

The reference policy was engineered for these mechanisms. Repeating seeds does
not establish unseen-fault generalization. HTTP 200 does not establish correct
prices, absence of side effects, or durable recovery. The stronger next test is
a pinned live Mistral model against a capable iterative comparator with explicit
experiment, token, and latency budgets, including unfamiliar and ambiguous faults.

## Reproduce and inspect

```sh
docker compose --profile eval run --build --rm eval \
  incidentlab-adaptive-eval --strategies adaptive,ordered \
  --seeds 11,23,37 --max-experiments 4 \
  --output artifacts/adaptive-comparison.json
```

The [tracked summary](results/adaptive-results.json) records the manifest, its SHA-256,
environment, aggregate results, limitations, and full-artifact digest. The
generated `artifacts/adaptive-comparison.json` contains the per-case experiments,
decision traces, failures, and verification evidence; timestamps and request
latencies naturally change on rerun. Failed arms remain in the denominator.
The Docker integration suite passed **170 tests** in 33.22 seconds.

For an explicitly enabled live arm and price configuration, see the
[Mistral integration guide](../career/MISTRAL_FDE.md). The broader-budget exhaustive versus
one-shot result is a separate [comparison](REHEARSAL_EVALUATION.md).
