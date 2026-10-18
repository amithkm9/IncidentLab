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
- Optional [Recovery Proof](docs/architecture/recovery-proof.md): same-snapshot
  full-plan/control/action-removal measurements, up to 36 checkout requests,
  zero model calls, per-action necessity findings, unsigned digest, and separate
  current-authority checks. Existing failed proofs block rehearsal promotion.
- Indexed SQLite history, atomic record/event transactions, persistent audit
  timelines, legacy JSON import, and JSON/Markdown exports.
- Responsive workbench with **Try the silent-failure demo**, expected-versus-observed
  checks, searchable evidence/history, outcome filters, and archived records.
- Strict TypeScript/Vite frontend source with a separate generated production
  build; evaluation modules, tests, and documentation grouped by responsibility.
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
[the semantic evaluation](docs/evaluation/semantic-evaluation.md) for denominators,
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

[Hosted CI for the reviewed implementation](https://github.com/amithkm9/IncidentLab/actions/runs/39114644943)
passed on `bc8fe51`: Docker/frontend builds, 345 backend tests, 47 frontend tests,
Python quality checks, and all four offline evaluation smoke runs. The complete
log contained zero warning lines. The subsequent audit-closure commit changes
only documentation.

The current Docker suite passed **345 tests in 44.36 seconds**, with warnings
promoted to errors. Coverage includes real HTTP flows, contracts, proof omissions,
incomplete measurements, stale authority, export integrity, promotion guards,
and frontend asset delivery. The TypeScript frontend passed strict type checking,
ESLint, Prettier, **47 Vitest tests**, and its production build on Node 24 in Docker.
Ruff lint and formatting checks passed for all 53 Python source/test files.
A same-origin POST through the Vite development proxy also completed a verified
checkout request; the temporary development server was stopped after the check.

The follow-up [codebase and security audit](docs/development/codebase-audit.md)
added Host/Origin validation, bounded API bodies, no-store responses, sanitized
errors/exports, and safe legacy-record handling. The frontend validates consumed
response fields and recovery consistency, encodes artifact URLs, and locks
mutations until a failed refresh is resolved. Twenty-one fresh offline API
responses passed the new validators, and legacy v0.1 archive fixtures remain
readable. Reorganized contracts, lab, investigation, and recovery modules retain
their original behavior apart from documented security fixes.

The Docker build no longer installs `uv` using root `pip`; it copies the pinned
binary from Astral's official image. Fresh app/test builds completed without
warnings. npm audit and pip-audit reported zero known dependency advisories
(26 locked Python packages, including development dependencies). Bandit flags
were reviewed, not suppressed. No unused runtime frontend exports/files or
runtime import cycles were found. The requested Codex Security Cloud extension
has no configured environment in this account and its app surface was unavailable;
**no cloud scan ran**. The app remains a local demo without authentication, tenant
isolation, or lifetime observation/history retention limits.

The rebuilt Safari app completed another offline demo, adaptive rehearsal,
36-response proof, and promotion with **five fresh contract passes**. The proof
became read-only after promotion. Desktop rendering was inspected after splitting
styles; the compiled CSS hash was unchanged. Wheel and source archives were
rebuilt; extracted-wheel checks loaded all four evaluation modules, six runbooks,
and four referenced frontend assets, and verified the Host guard/no-store header.
An exact-key scan found no configured credential in 144 publishable files or
archives; the ignored environment file retained mode 0600. Published evaluation
JSON artifacts remain byte-for-byte unchanged.

The Starlette TestClient warning came from its legacy `httpx` fallback. The
locked development dependency now supplies `httpx2`; runtime Mistral clients
retain `httpx`. Enabling warnings-as-errors exposed unclosed HTTP error response
streams in dependency, probe, and health checks. Those paths and a test-owned
response now close explicitly. A retained-response regression checks immediate
closure; 31 focused tests also passed with allocation tracing enabled. No warning
suppression was added.

The first hosted CI run also passed, but exposed Node 20 action-deprecation
annotations. Checkout and artifact upload now use their Node 24-based v7
releases. CI pins Ubuntu 24.04 to avoid an implicit runner-image migration,
uses read-only repository permissions, and does not persist checkout credentials.

All four reorganized evaluation commands completed their offline smoke runs:

| Runner | Measured smoke result |
| --- | --- |
| Baseline | 7/7 completed; five actionable cases recovered and two controls preserved |
| Rehearsal | 8/8 faults recovered versus 5/8 single-fix baseline; both preserved 2/2 controls |
| Adaptive | 8/8 faults with 11 candidates versus 4/8 with 26 fixed-order candidates; both preserved 2/2 controls |
| Semantic | 24 paired trials; three of 13 HTTP-only acceptances violated the contract; adaptive recovered 4/4 faults and preserved 2/2 controls |

These are regression checks of known local scenarios, with no provider calls.
Smoke reports are generated under `artifacts/`; the earlier full evaluation
records above remain unchanged. Timings from concurrently run smoke commands
are not used as comparative performance claims.

The earlier Safari walkthrough exercised the compiled TypeScript app through demo,
adaptive rehearsal, proof, expanded response details, and explicit promotion.
The [saved proof](docs/evaluation/results/recovery-proof-route-price.json)
contains four trials and 36 responses: the combined plan passed, omitting the
route fix failed availability, and omitting rollback produced nine HTTP 200s
with nine incorrect prices. Export integrity passed; the active source stayed
unchanged until promotion. The UI then reported five fresh contract passes and
marked the proof read-only historical evidence.

The desktop proof layout and the Chrome **390 × 844** workbench were visually
inspected. The mobile header, navigation, controls, and health cards fit; the
inspected Chrome console had zero messages. This is a browser-emulation spot
check, not a complete mobile-device or accessibility audit. The retained
[dashboard capture](docs/assets/semantic-console.png) predates this migration;
[Recovery Proof's diagram](docs/assets/recovery-proof.svg) documents the new flow.
The earlier rehearsal capture remains explicitly historical.

Wheel and source-distribution builds passed. The wheel contains the compiled
frontend, evaluation modules, and benchmark manifest; an extracted-wheel
TestClient check served its bundled index and all referenced assets. Final
archive inspection found no legacy JavaScript frontend, environment file,
node_modules, or runtime data. Publishable source and generated frontend were
scanned for the configured key; none contained it. JSON, SVG, and relative
documentation links were checked.

The host shell restricts loopback HTTP, so integration execution uses Docker.
Mocked provider tests validate integration contracts and failure handling;
actual live quality remains the separately reported results above. This pass
made no additional paid model calls.

## Historical benchmark evidence · October 17, 2026

These artifacts used the original HTTP-status recovery definition and ten
scenario families. They predate the independent contract and silent-price
scenarios:

- Original baseline: 105/105 correct causes/actions, 75/75 HTTP-verified
  recoveries, and 30/30 no-action controls.
  [Baseline evidence](docs/evaluation/baseline-results.md)
- Exhaustive rehearsal: 24/24 recoveries versus 15/24 for one-shot remediation,
  including 9/9 versus 0/9 compound recoveries; both preserved 6/6 controls.
  Rehearsal used 405 candidates and 1,305 experiment requests.
  [Rehearsal evidence](docs/evaluation/rehearsal-evaluation.md)
- Offline adaptive policy: 24/24 faults recovered in 33 candidates versus 12/24
  in 78 candidates for a simple fixed order; both preserved 6/6 controls.
  [Adaptive evidence](docs/evaluation/adaptive-evaluation.md)

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

[CV wording](docs/career/cv.md) · [Customer-pilot approach](docs/career/mistral-fde.md)
