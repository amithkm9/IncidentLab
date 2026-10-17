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
- Responsive recovery workbench with diagnosis, rehearsal, evidence, and history.
- Two reproducible benchmark runners, Docker Compose, and CI artifact generation.

## Verification

- Final integrated Docker suite: **90 passed**, 24.82 seconds. Covers real
  HTTP/SQLite errors and recovery, clone isolation and cleanup, partial repairs,
  stale/drifted plans, restart safety, persistence, and evaluator accounting.
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

Chrome desktop walkthrough verified compound-fault injection, investigation,
citation-to-log navigation, all 15 rehearsal outcomes, two-action promotion with
five fresh HTTP 200 responses, persistent history, and disabled archive actions.
JavaScript syntax, Python compilation, and Git whitespace checks passed. Final
copy/typography refinements were reviewed in code; a separate mobile viewport
visual check remains outstanding. Responsive layouts and keyboard tab navigation
are implemented.

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

Next: credentialed Mistral evaluation; an equal-budget iterative baseline;
nonrecoverable and ambiguous faults; semantic outcome assertions; engineer
feedback. Production adapters and stateful distributed-service cloning are
separate work. No production deployment, customer study, reduced-MTTR result,
or first-ever novelty claim is made. See [docs/CV.md](docs/CV.md) for defensible
portfolio wording.
