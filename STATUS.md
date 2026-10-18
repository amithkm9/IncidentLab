# IncidentLab status

Updated: 2026-10-18. Version: 0.2.0.

## Implemented

- Real checkout and inventory HTTP services backed by a SQLite catalog.
- Twelve reproducible scenarios: six single-fault variants, four masked compound
  failures, and healthy/missing-telemetry controls.
- Independent `checkout-response` contract, version `1.0.0`, with expected
  products and exact prices, strict response validation, and a recorded SHA-256.
- Availability and business correctness tracked separately. Silent price drift
  returns HTTP 200 but fails the contract; route-plus-price drift exposes that
  failure only after the route is repaired.
- Read-only offline and bounded Mistral investigators with citations and BM25
  runbooks; scenario labels and evaluator answers stay outside model context.
- Actual-state snapshots using SQLite backups, independent clone ports, and
  isolated control/one-action/two-action experiments.
- Exhaustive comparison plus adaptive selection through an offline policy or
  Mistral Conversations. Validated local tools, decision trails, explicit
  failure/abstention, bounded experiments, and provider usage accounting.
- Promotion guarded by episode, revision, and a state fingerprint that includes
  the contract. Five fresh requests must pass HTTP and declared business rules.
- Indexed SQLite history, atomic record/event transactions, persistent audit
  timelines, legacy JSON import, and JSON/Markdown exports.
- Responsive workbench with **Try the silent-failure demo**, expected-versus-observed
  checks, searchable evidence/history, outcome filters, and archived records.
- Pictorial documentation with actual app captures, architecture and recovery
  diagrams, four evaluation runners, Docker Compose, and CI artifact generation.

## Current semantic evaluation

The offline test completed **18 episodes**, including 12 faults and six controls.
Across **72 paired trials / 216 requests**, HTTP-only acceptance passed 39 trials,
while the contract accepted 30. **Nine HTTP-only acceptances were false
recoveries** under the contract: **23.08% of 39**.

The separate offline adaptive recovery arm restored **12/12 faults**, preserved
**6/6 no-action controls**, and used **18 candidate experiments**. These are
controlled known-scenario results; the paired acceptance test and policy
recovery test answer different questions. See
[docs/SEMANTIC_EVALUATION.md](docs/SEMANTIC_EVALUATION.md) for denominators,
protocol, and recorded evidence.

The first live smoke run, pinned to `mistral-small-2603`, recovered **1/4 fault
cases**, preserved **2/2 no-action controls**, and recorded **two provider
errors**. A compound case also exposed a plan that dropped a required prior
repair. The follow-up with explicit full-plan context also recovered **1/4 faults**,
preserved both controls, and recorded **three HTTP 429 failures**. Both reports
are retained. Safe provider categories/status/retry metadata are now exported
and shown in the UI; no automatic provider retries or live improvement is claimed.

Live credentials are configured locally in an ignored environment file.
Credentials are not part of tracked source or benchmark summaries.

## Validation

The integrated Docker suite passed **251 tests in 38.94 seconds**, including
the semantic contracts, real HTTP flows, provider-error metadata, and full-plan
experiment context. JavaScript syntax and provider-diagnostic bounds were also
checked after the responsive UI changes.

The current contract-aware dashboard screenshot was captured from the running
app and visually inspected:
[semantic-console.png](docs/assets/semantic-console.png). The new semantic
recovery diagram was rendered and checked for label fit. The earlier desktop
and mobile screenshots document the previous UI state.

The current browser walkthrough verified a route-only repair returning five
HTTP 200 responses while all five price checks failed. A fresh compound rehearsal
then measured the failed route-only plan and passing combined plan. Safari
confirmed promotion and five fresh HTTP/price/SKU passes.

Mobile sizing was hardened for shrinking grid tracks and wrapped controls. The
new Chrome390px capture showed clipping and stale rendering even across window
changes; the final mobile visual check is inconclusive. The old mobile capture
is explicitly historical and is not evidence of this upgrade's mobile layout.

The host shell blocks local HTTP binding, so real-HTTP execution runs in Docker.
An upstream Starlette warning concerns the httpx TestClient adapter. Mocked
provider tests validate integration contracts and failure handling; actual live
quality is reported separately above.

## Historical benchmark evidence · October 17, 2026

These artifacts used the original HTTP-status recovery definition and ten
scenario families. They predate the independent contract and silent-price
scenarios:

- Original baseline: 105/105 correct causes/actions, 75/75 HTTP-verified
  recoveries, and 30/30 no-action controls.
  [Baseline evidence](docs/BASELINE_RESULTS.md)
- Exhaustive rehearsal: 24/24 recoveries versus 15/24 for one-shot remediation,
  including 9/9 versus 0/9 compound recoveries; both preserved 6/6 controls.
  Rehearsal used 405 candidates and 1,305 experiment requests.
  [Rehearsal evidence](docs/REHEARSAL_EVALUATION.md)
- Offline adaptive policy: 24/24 faults recovered in 33 candidates versus 12/24
  in 78 candidates for a simple fixed order; both preserved 6/6 controls.
  [Adaptive evidence](docs/ADAPTIVE_EVALUATION.md)

The earlier integrated suite passed 170 tests. These historical measurements
remain useful regression records and must not be relabeled as current semantic
or live-model results.

## Interpretation and next work

The contract verifies declared product, price, and response-shape requirements.
It does not establish unspecified business correctness, external side-effect
safety, long-term reliability, or production rollout safety. Repeated seeds
exercise known mechanisms; they are not independent production incidents.

Next work targets the observed provider and compound-plan failures, fresh pinned
live comparisons, broader business invariants, a stronger iterative baseline,
and engineer feedback. Production telemetry adapters and distributed-service
cloning require separate work. No customer study, production deployment,
reduced-MTTR result, or first-ever novelty claim is made.

[CV wording](docs/CV.md) · [Customer-pilot approach](docs/MISTRAL_FDE.md)
