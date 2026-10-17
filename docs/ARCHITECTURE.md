# IncidentLab architecture

IncidentLab runs a deliberately small but real application: checkout calls an
inventory HTTP service and reads a SQLite catalog. The application is designed
to fail in observable ways so diagnosis, remediation, and verification can be
measured end to end.

![IncidentLab architecture and isolated recovery workflow](assets/architecture.svg)

## Component map

| Path | Responsibility |
| --- | --- |
| `src/incidentlab/lab.py` | Checkout and inventory HTTP servers, SQLite catalog, ten scenarios, actual-state snapshots, independent clone lifecycle |
| `src/incidentlab/rehearsal.py` | Bounded intervention search, no-action control, measured selection of the smallest successful plan |
| `src/incidentlab/investigator.py` | Deterministic offline rules and bounded Mistral adapter |
| `src/incidentlab/tools.py` | Typed read-only tool schemas, evidence collection, lexical BM25 runbook search |
| `src/incidentlab/service.py` | Episode lifecycle, mutation serialization, promotion guards, report generation |
| `src/incidentlab/store.py` | Indexed SQLite history and atomic record/event transactions |
| `src/incidentlab/api.py` | FastAPI endpoints and static interface |
| `src/incidentlab/static/` | Buildless browser UI with no CDN dependencies |
| `src/incidentlab/evaluate.py` | Frozen single-fault suite and trace reports |
| `src/incidentlab/evaluate_rehearsal.py` | Single-fix versus rehearsal comparison |
| `tests/` | Real-HTTP integration tests and mocked Mistral contract tests |

## Observation and authority

The investigator receives observations, not the injected scenario or expected
answer. Operator controls and evaluator ground truth stay outside its context.
Its tools can read logs, metrics, health, recent changes, and runbooks. They
cannot execute arbitrary code or apply remediation.

Diagnosis validation checks typed output, allowed cause/action pairs, and
observed citation IDs. It does not prove that every claim follows from those
citations. Runbook text supplies guidance, not evidence that a failure occurred.

The API accepts a single proposed fix only when it matches the current finding
and lab revision. Older findings and repeat actions are rejected. Mutating
workflows are serialized per lab. FastAPI's
[lifespan mechanism](https://fastapi.tiangolo.com/advanced/events/) owns the HTTP
lab and shuts its servers down when the app stops. One app process owns one lab;
run a single worker.

## Isolated fix rehearsal

1. Snapshot the current configuration, fault state, and database. SQLite's
   backup API captures the catalog, including partial repairs already made.
2. Create independent HTTP/SQLite copies on separate loopback ports. Measure a
   no-action control and all allowed one-action and two-action combinations:
   five individual fixes and ten pairs at the default two-action setting.
3. Send fresh checkout requests to each copy and retain unsuccessful outcomes.
   Choose a shortest passing plan only when the control is failing and
   diagnostic telemetry is available. Healthy controls require no change;
   missing telemetry requires abstention.
4. Require explicit operator promotion. Check the originating episode, revision,
   and SHA-256 state fingerprint against the current lab. Apply only the
   recommended, measured plan while those checks remain valid.
5. Begin a new observation window and issue five fresh verification requests.
   Old failed traffic cannot contaminate the new window's verification.

All candidate experiments start from the same actual-state snapshot. The search
does not inspect scenario labels or expected actions. Each temporary clone is
closed after its experiment; the source lab remains unchanged during rehearsal.

The search is bounded to five known actions and at most two actions per plan.
This implementation copies a purpose-built local HTTP/SQLite application, not
production infrastructure. Passing a small sample of HTTP 200 responses does not
establish semantic correctness, absence of side effects, long-term reliability,
or production safety.

## Persistence and exports

Records and append-only audit events are stored in `runtime/history.sqlite`.
Version 0.1 JSON records are imported once without replacing newer records.
The UI can reopen saved findings and rehearsal outcomes, download JSON records,
and generate Markdown incident reports containing evidence and verification.

Current lab authority stays in memory. Page reloads can restore the current
workspace. Restarting the server creates a new episode while preserving
read-only history, so a historical finding cannot authorize a mutation in the
new lab. The Docker `lab-runtime` named volume retains these records.

## Investigation modes

| Mode | Initial observations | Retrieval | Model-directed tools |
| --- | --- | --- | --- |
| `baseline` | Metrics, logs, health, changes | Lexical BM25 | None; deterministic rules |
| `prompt` | Three checkout logs and metrics | None | None |
| `retrieval` | Same initial snapshot | One BM25 search | None |
| `mistral` | Same initial snapshot | Available as a tool | Up to 16 calls across 8 API turns |

All model modes require a live `MISTRAL_API_KEY`. Errors never silently fall back
to the baseline. The adapter follows Mistral's
[function-calling interface](https://docs.mistral.ai/studio/conversations/function-calling).
`MISTRAL_MODEL` defaults to `mistral-small-latest`; pin an available provider
model version for repeatable comparisons.

Set the key in the server environment. Docker Compose reads a local `.env` file;
the Python CLI does not automatically load one. Do not put credentials in browser
code or commit `.env`. The frontend receives only a configuration flag.

Model runs record tokens and latency. Estimated cost is recorded only when
`MISTRAL_INPUT_USD_PER_MILLION` and `MISTRAL_OUTPUT_USD_PER_MILLION` are configured
with appropriate prices. Otherwise cost remains unknown. No live Mistral run is
represented by the recorded offline benchmark results.

## Validation and evaluation

With Python and uv:

```sh
uv run --extra dev pytest -q
uv run incidentlab-eval --mode baseline --split smoke
uv run incidentlab-eval --mode baseline --split test
uv run incidentlab-rehearsal-eval --split test
```

With Docker:

```sh
docker compose --profile test run --build --rm test
docker compose --profile eval run --build --rm eval incidentlab-eval --mode baseline --split test
docker compose --profile eval run --build --rm eval incidentlab-rehearsal-eval --split test
```

On Linux, prefix the evaluation command with `LOCAL_UID="$(id -u)"
LOCAL_GID="$(id -g)"` if the mounted artifact directory has different ownership.

The original frozen manifest has 7 smoke cases, 21 development cases, and 105
test cases. These are known single-fault regression cases, including healthy and
missing-telemetry controls. Each run saves per-case findings, tool traces,
recovery responses, a manifest hash, and environment metadata under `artifacts/`.
See [evaluation methodology](EVALUATION.md) and the
[recorded baseline results](BASELINE_RESULTS.md).

The separate rehearsal comparison has 30 cases: 15 single faults, nine compound
faults, and six controls. Both arms retain failures in metric denominators.
Rehearsal receives a larger experiment and action budget than the one-shot
baseline. See [the full protocol and measured results](REHEARSAL_EVALUATION.md)
for denominators, timing scope, resource cost, and limitations.

After configuring credentials, compare model modes with:

```sh
uv run incidentlab-eval --mode prompt --split test
uv run incidentlab-eval --mode retrieval --split test
uv run incidentlab-eval --mode mistral --split test
```

These commands make paid API calls. Each complete test run has 105 cases; start
with `--split smoke` to check the integration. Seed splits repeat known
mechanisms and do not establish generalization to unseen fault families.

## Next comparisons

An equal-budget iterative diagnosis baseline would help separate the value of
experimentation from the extra action and request budget. Live Mistral
evaluation, semantic checks beyond HTTP status, ambiguous faults, and engineer
feedback would strengthen the evidence further. Production telemetry adapters,
richer stateful services, and deployment rollback require separate engineering.

[Back to the project overview](../README.md)
