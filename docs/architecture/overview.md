# Architecture reference

The [README](../../README.md#architecture) contains the system diagram, recovery
sequence, demo, and operating boundaries. This reference maps those behaviors to
code and records implementation details needed to review or extend them.

## Component map

| Source | Responsibility |
| --- | --- |
| `api/app.py` | FastAPI endpoints and HTTP error mapping |
| `api/security.py`, `api/frontend.py` | Browser-origin protections, security headers, and compiled frontend delivery |
| `application.py` | Episode lifecycle, serialized mutations, current-plan authority, proof coordination, report generation |
| `domain/models.py`, `domain/contracts.py` | Typed requests/results and immutable independent checkout requirements |
| `lab/environment.py` | Checkout and inventory HTTP servers, SQLite catalog, measurements, and clone lifecycle |
| `lab/scenarios.py`, `lab/snapshot.py` | Controlled failure definitions and actual-state snapshot representation |
| `investigation/agents.py`, `investigation/tools.py` | Deterministic or Mistral investigation, typed read-only tools, lexical BM25 retrieval |
| `investigation/runbooks/` | Local diagnostic guidance; not evidence that a failure occurred |
| `recovery/rehearsal.py` | Bounded exhaustive search and measured selection |
| `recovery/adaptive.py` | Sequential experiments, Mistral Conversations tools, observation sanitization, usage accounting |
| `recovery/proof.py` | Full-plan/control/action-removal measurements, consistency checks, necessity findings, unsigned digests |
| `storage.py` | Indexed SQLite records and atomic record/event transactions |
| `evaluation/` | Baseline, rehearsal, adaptive, and semantic comparisons; frozen manifests and scoring |
| `frontend/src/` | TypeScript domain types, API client, state/controller, views, and styles |

Backend paths above are relative to `src/incidentlab/`. The API, domain, lab,
investigation, and recovery packages separate distinct responsibilities;
evaluation owns answer keys and scoring outside the product's planner context.
Frontend output is generated into `frontend/dist/` and bundled as `incidentlab/web`
in wheels. [Build and development details](../development/README.md)

## Observation and authority

Investigators receive observed logs, metrics, health, recent changes, and
runbooks. They do not receive scenario labels or evaluator answers, and their
tools cannot execute arbitrary code or apply a repair. Typed finding validation
checks allowed cause/action pairs and observed citation IDs. It does not prove
that every statement logically follows from the citations.

Single-fix remediation must match the current finding and revision; older
findings and repeat attempts are rejected. Rehearsal promotion must match the
current recommended measured plan, episode, revision, and source fingerprint.
The fingerprint includes contract metadata. Mutations are serialized per lab.

FastAPI's [lifespan](https://fastapi.tiangolo.com/advanced/events/) owns the local
HTTP servers and closes them on shutdown. One app process owns one lab; use a
single worker. Production multi-process coordination is outside this design.

## Snapshot and experiment semantics

A snapshot captures actual configuration, fault state, database, and contract.
SQLite's backup API includes partial repairs already made. Every candidate starts
from that same source state on independent loopback ports; it cannot inherit a
previous experiment's changes. Each temporary clone closes after measurement.

| Strategy | Search behavior | Limits |
| --- | --- | --- |
| `exhaustive` | No-action control plus all allowed single fixes and pairs | Five single fixes and ten pairs at the two-action setting |
| `adaptive` | Engineered offline policy selects its next plan from observed errors | Default four candidates; API accepts one to eight |
| `mistral` | Model selects experiments using the same measured feedback | Same candidate limit; bounded provider requests and scheduling deadline |

All plans have at most two actions. Healthy controls require no change;
unavailable diagnostic telemetry requires abstention. Adaptive controls that
meet either condition stop before constructing or calling the model. The
exhaustive strategy ignores the adaptive candidate ceiling and performs its
complete bounded search.

Fresh response validation decides success. A recommendation is shortest among
the successful plans actually tested; adaptive search does not establish a
global minimum over unsearched alternatives. Promotion begins a new observation
window and checks five new active-lab responses, so earlier failed traffic does
not contaminate final verification.

The [contract specification](semantic-recovery.md) defines exact validation and
stored fields. [Recovery Proof](recovery-proof.md) records its additional
same-snapshot trials, request accounting, action-necessity interpretation,
optional-check behavior, and current-authority rules. Failed proof measurements
remain evidence and block that rehearsal's promotion.

## Adaptive Mistral interface

`POST /api/rehearse` accepts `strategy`, `max_experiments`, `max_actions`, and
`probe_count`. Fresh clone observations include measured errors, product IDs,
expected/observed amounts, logs, metrics, and health. Paths, endpoints, raw
configuration, scenario labels, and evaluator answers are excluded. The action
catalog explains actual tool effects, including the difference between catalog
path restoration and pricing rollback.

The adapter uses stateless `/v1/conversations` calls with `store: false`.
Locally retained `function.call` and `function.result` entries connect each
proposal with its measured result. `rehearse_plan` and `stop_rehearsal` are the
only planner tools; neither promotes a change. Python enforces strict schemas,
allowed actions, observed citations, duplicate detection, and experiment limits.

A 120-second scheduling deadline prevents new calls or trials after expiry;
in-flight requests have bounded timeouts. Reports retain decisions, completed
experiments, started-attempt counts, stop reason, errors, and provider usage.
Invalid decisions, provider errors, or execution failures authorize no new plan;
there is no silent offline fallback. Short hypotheses are stored, but private
model reasoning is neither requested nor displayed.

## Investigation modes

| Mode | Initial observations | Retrieval | Model-directed tools |
| --- | --- | --- | --- |
| `baseline` | Metrics, logs, health, changes | Lexical BM25 | None; deterministic rules |
| `prompt` | Three checkout logs and metrics | None | None |
| `retrieval` | Same initial snapshot | One BM25 search | None |
| `mistral` | Same initial snapshot | Available as a tool | At most 16 calls across eight API turns |

Model modes require a configured server key and follow Mistral's
[function-calling interface](https://docs.mistral.ai/studio/conversations/function-calling).
Pin an available model version for repeatable comparisons. Usage records include
reported tokens and latency; dollar estimates require explicit input/output
prices. Unreported usage from failed requests remains unknown.
[Setup and cost configuration](../../README.md#quick-start) ·
[Integration and customer-pilot discussion](../career/mistral-fde.md)

## Persistence and exports

Records and audit events live in `runtime/history.sqlite`; record/event updates
are atomic. Legacy version 0.1 JSON records import once without replacing newer
records. History supports reopening findings, experiments, and proof artifacts,
and exports JSON evidence plus Markdown incident reports.

Current mutation authority stays in memory. Page reloads restore the workspace;
a server restart creates a new episode while retaining read-only history. The
Docker `lab-runtime` volume keeps the database across app restarts. A valid saved
artifact does not authorize a change in a later episode.

## Validation and evaluation

The [README check commands](../../README.md#run-the-checks) cover the common
workflow. Detailed methods and unchanged historical evidence live in the
[evaluation references](../README.md#evaluation). New reports record manifests,
hashes, observations, outcomes, environment metadata, and resource accounting.

```sh
uv run incidentlab-eval --mode baseline --split smoke
uv run incidentlab-eval --mode baseline --split test
uv run incidentlab-rehearsal-eval --split test
uv run incidentlab-adaptive-eval --seeds 11,23,37 --max-experiments 4
uv run incidentlab-semantic-eval --split test --strategies adaptive
```

Run these commands in Compose's `eval` service if the host cannot bind loopback
ports. On Linux, set `LOCAL_UID` and `LOCAL_GID` to your numeric IDs when the
mounted artifact directory has different ownership. Live baseline-comparison
modes (`prompt`, `retrieval`, `mistral`) make paid requests; start with the smoke
split after explicit setup. Semantic/adaptive live comparisons also require
`--allow-paid-api`.

Seed splits repeat known failure mechanisms, not unseen incident families.
Offline policies, live models, paired acceptance gates, and historical HTTP-only
comparisons have distinct denominators and must remain separately labeled.
