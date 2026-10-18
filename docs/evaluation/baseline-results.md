# Offline baseline results — 2026-10-17

**These are deterministic rule-based baseline results, not Mistral model scores.**
The baseline was implemented for these known fault families. This run verifies
end-to-end regression behavior; it does not establish unseen-fault or production
diagnostic accuracy.

Command:

```sh
docker compose --profile eval run --rm eval incidentlab-eval --mode baseline --split test
```

Run: 2026-10-17 13:16:00–13:16:14 UTC. Full per-case evidence and recovery records:
`artifacts/baseline-test.json` (1,016,519 bytes; generated locally and ignored by
Git). Keep that artifact alongside this summary when sharing the result.

| Measure | Observed result |
| --- | --- |
| Attempted / completed episodes | 105 / 105 |
| Episode errors | 0 |
| Correct causes | 105 / 105 |
| Correct actions | 105 / 105 |
| Verified recoveries on actionable faults | 75 / 75 |
| Appropriate abstention on missing telemetry | 15 / 15 |
| No-action decisions on healthy/missing-telemetry controls | 30 / 30 |
| Median / p95 investigator latency | 0.85 ms / 3.71 ms |
| Model API calls and tokens | 0 |
| Semantic support of claims | Not measured automatically |

Each fault family has 15 seeds. The five actionable families each recovered in
all 15 cases, with five fresh HTTP 200 responses required for each recovery.
The healthy and missing-telemetry controls each produced no action in all
15 cases. Seeds repeat the same underlying mechanisms with limited variation;
these are not independent samples of real incidents.

Latency covers only the investigator and its read-only tools, excluding fault
injection, traffic generation, and recovery. This is a small local rule engine;
its timing is not representative of a model-backed service.

Environment: Python 3.11.17, Linux 6.12.54 linuxkit aarch64, glibc 2.41;
FastAPI 0.143.3, httpx 0.28.1, Pydantic 2.14.1. Dependency resolution is recorded
in `uv.lock`.

Frozen manifest SHA-256:

```text
2907976c098e88c1a3aaa342c34b655ab01e6982f402cdde2c6b4b89b64bfceb
```

At the time of this run, the automated suite separately passed 39 tests,
including provider contract tests with mocked Mistral responses. Live Mistral
connectivity and performance had not yet been checked because no key was
configured. Later Conversations measurements are retained in the
[semantic evaluation](semantic-evaluation.md). See the
[baseline methodology](baseline-methodology.md) for this run's definitions.
