# IncidentLab status

Updated: 2026-10-17. Version: 0.2.0.

## Implemented

- Checkout and inventory HTTP services with a real SQLite catalog.
- Five single-fault families, three masked compound faults, healthy and
  missing-telemetry controls: ten reproducible scenarios in total.
- Read-only offline and bounded Mistral investigators with citations and BM25
  runbooks. The model does not receive injected scenario labels.
- Actual-state snapshots, SQLite backup-based copying, independent clone ports,
  and isolated control/one-action/two-action experiments.
- Minimal passing plan selection from measured traffic; explicit promotion with
  episode, revision, and state-fingerprint checks, followed by fresh verification.
- Indexed SQLite history, atomic record/event transactions, persistent audit
  timelines, legacy JSON import, and JSON/Markdown incident report exports.
- Responsive recovery workbench with a guided offline demo, searchable evidence
  and history, outcome filters, linked archived experiments, and mobile plan cards.
- Visual README with actual desktop/mobile screenshots and architecture, workflow,
  and benchmark diagrams; detailed technical reference in `docs/ARCHITECTURE.md`.
- Adaptive experiment selection with an offline reference policy and a Mistral
  Conversations adapter, validated local tools, bounded experiments, explicit
  abstention/failure outcomes, decision trails, and provider usage accounting.
- Three reproducible benchmark runners, Docker Compose, and CI artifact generation.

## Verification

- Final integrated Docker suite: **170 passed**, 33.22 seconds. Covers real
  HTTP/SQLite errors and recovery, clone isolation and cleanup, partial repairs,
  stale/drifted plans, restart safety, persistence, evaluator accounting, adaptive
  selection, invalid provider decisions, deadline/budget enforcement, and API usage.
- Adaptive comparison: **30 cases, zero execution errors**, with a four-candidate
  ceiling per arm. Offline adaptive policy recovered **24/24 faults**, including
  **9/9 compound cases**, using **33 candidates**; fixed-order search recovered
  **12/24** using 78. Both preserved **6/6 controls**. This is a known-error policy
  versus a simple fixed prefix, not a live model score. See
  [docs/ADAPTIVE_EVALUATION.md](docs/ADAPTIVE_EVALUATION.md).
- Rehearsal test split: **30 episodes, zero execution errors**. On 24 actionable
  fault cases, one-shot baseline recovery was **15/24 (62.5%)**; rehearsal was
  **24/24 (100%)**, an improvement of **37.5 percentage points**.
- Compound fault recovery: **0/9 versus 9/9**. Both workflows made no change on
  **6/6 controls**. Rehearsal measured **405 candidate experiments**, 30 controls,
  and 1,305 experiment requests.
- Full evidence: `artifacts/rehearsal-test.json`. Methodology and a versioned
  summary are in [docs/REHEARSAL_EVALUATION.md](docs/REHEARSAL_EVALUATION.md).
- The original v0.1 baseline suite measured 105/105 correct causes/actions,
  75/75 recoveries, and 30/30 control no-action decisions. Those results cover
  the original known single-fault families; see [docs/BASELINE_RESULTS.md](docs/BASELINE_RESULTS.md).

Chrome and Safari desktop walkthroughs verified compound-fault investigation,
citation-to-log navigation, evidence search and empty states, all 15 rehearsal
outcomes plus the control, the passing-plan filter, two-action promotion with
five fresh HTTP 200 responses, history search, and read-only archive inspection.
Chrome's 390-pixel responsive viewport was visually checked for stacked forms,
readable findings, full-width actions, and experiment comparison cards. This is
browser viewport testing, not a physical-device test. Safari select-field sizing
was corrected and checked. Actual app screenshots and rendered SVG diagrams
were inspected for the README. JavaScript syntax, static HTML/ARIA references,
local documentation links, and Git whitespace checks passed.

The adaptive upgrade was separately exercised in Safari: a one-candidate budget
withheld promotion after the partial repair; a four-candidate ceiling found the
two-action plan in two trials, then promotion returned five fresh HTTP 200s.
Chrome restored that saved result and displayed its complete decision trail at
390 pixels with wrapped plans, hypotheses, and evidence IDs. No live provider
calls were made during browser verification.

The upgraded Docker app is healthy at `http://127.0.0.1:8000`; the runtime volume
preserves history. Use `docker compose stop app` to stop it.

The host shell blocks local HTTP binding, so real-HTTP execution runs in Docker.
One upstream Starlette warning concerns the httpx TestClient adapter; no checks
are skipped because of it. Live Mistral credentials are not configured: mocked
adapter tests verify the protocol, not live API access or model performance.

## Interpretation and next work

The expanded workflow uses a larger action/experiment budget than the one-shot
baseline. Cases repeat ten known mechanisms across three seeds; they are not
independent production incidents or unseen-fault generalization tests. Passing
HTTP requests do not establish semantic correctness or production safety.

Next: credentialed Mistral evaluation; a stronger iterative baseline;
nonrecoverable and ambiguous faults; semantic outcome assertions; engineer
feedback. Production adapters and stateful distributed-service cloning are
separate work. No production deployment, customer study, reduced-MTTR result,
or first-ever novelty claim is made. See [docs/CV.md](docs/CV.md) for defensible
portfolio wording.
