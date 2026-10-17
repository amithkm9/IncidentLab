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
| `src/incidentlab/adaptive.py` | Evidence-driven sequential experiments, bounded Mistral Conversations tools, sanitized observations and usage accounting |
| `src/incidentlab/investigator.py` | Deterministic offline rules and bounded Mistral adapter |
| `src/incidentlab/tools.py` | Typed read-only tool schemas, evidence collection, lexical BM25 runbook search |
| `src/incidentlab/service.py` | Episode lifecycle, mutation serialization, promotion guards, report generation |
| `src/incidentlab/store.py` | Indexed SQLite history and atomic record/event transactions |
| `src/incidentlab/api.py` | FastAPI endpoints and static interface |
| `src/incidentlab/static/` | Buildless browser UI with no CDN dependencies |
| `src/incidentlab/evaluate.py` | Frozen single-fault suite and trace reports |
| `src/incidentlab/evaluate_rehearsal.py` | Single-fix versus rehearsal comparison |
| `src/incidentlab/evaluate_adaptive.py` | Adaptive and fixed-order policies at equal candidate ceilings, with an explicitly enabled live Mistral arm |
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

## Adaptive experiment selection

`POST /api/rehearse` accepts `strategy`: `exhaustive` (default), `adaptive`
(offline deterministic policy), or `mistral` (Conversations agent). Both adaptive
modes accept `max_experiments` from one to eight, independently of the one/two
action limit and requests per experiment. The exhaustive strategy ignores this
candidate ceiling and retains the existing complete bounded search.

The engine first measures a no-change control. Healthy or missing-telemetry
controls end without a planner call. Each proposed plan starts from the same
source snapshot, and the resulting clone supplies fresh logs, metrics, and
service-health evidence. Paths, endpoints, raw configuration, scenario labels,
and evaluator answers are excluded from planner observations.

The Mistral adapter uses stateless `/v1/conversations` calls with `store: false`.
Locally retained `function.call` and `function.result` entries connect each
decision to its measured result. The two tools are `rehearse_plan` and
`stop_rehearsal`; neither can promote a plan. Strict schemas, an action allowlist,
observed citation IDs, duplicate detection, and experiment limits are enforced
in Python. A 120-second scheduling deadline prevents starting another call or
experiment after expiry; in-flight requests use bounded timeouts.

The report preserves decisions, completed experiments, started-attempt counts,
stop reason, and reported model usage. Invalid decisions, provider failures, and
candidate execution failures authorize no new plan. There is no silent offline
fallback. The existing episode/revision/fingerprint promotion checks also apply
to adaptive reports. Short hypotheses are stored; private model reasoning is
not requested or displayed. A passing plan is smallest among the candidates
actually tested, not globally minimal over the unsearched alternatives.

[Mistral integration and FDE demonstration](MISTRAL_FDE.md)

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
uv run incidentlab-adaptive-eval --seeds 11,23,37 --max-experiments 4
```

With Docker:

```sh
docker compose --profile test run --build --rm test
docker compose --profile eval run --build --rm eval incidentlab-eval --mode baseline --split test
docker compose --profile eval run --build --rm eval incidentlab-rehearsal-eval --split test
docker compose --profile eval run --build --rm eval incidentlab-adaptive-eval --seeds 11,23,37
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

The new adaptive comparison gives an evidence-driven offline policy and a
fixed-order search the same candidate/probe ceiling. It does not equalize total
compute or model reasoning, and fixed-order search is a deliberately simple
comparator. Live Mistral evaluation against the adaptive policy, semantic checks
beyond HTTP status, ambiguous faults, and engineer feedback would strengthen
the evidence further. Production telemetry adapters, richer stateful services,
and deployment rollback require separate engineering.

[Back to the project overview](../README.md)
