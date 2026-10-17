# IncidentLab status

Updated: 2026-10-17.

## Implemented

- Disposable checkout and inventory HTTP services with a SQLite catalog.
- Five fault families plus healthy and unavailable-telemetry controls.
- Deterministic offline investigator; BM25 runbook search.
- Mistral prompt-only, retrieval-only, and bounded tool-calling modes.
- FastAPI orchestration, serialized operations, stale-finding remediation checks.
- Browser workflow with metrics, citations, tool traces, recovery, and JSON export.
- CLI, Docker Compose, frozen evaluation manifest, and automated tests.

## Verification

- `docker compose --profile test run --rm test`: **39 passed**, 5.88 seconds.
  Includes real HTTP/SQLite fault and recovery checks, API lifecycle and stale
  action rejection, and mocked Mistral tool-calling and failure paths.
- `docker compose --profile eval run --rm eval incidentlab-eval --mode baseline
  --split test`: **105/105** correct causes and actions, **75/75** verified
  recoveries, **30/30** control no-action decisions, no episode errors.
- JavaScript syntax and Python compile checks passed.
- Chrome desktop walkthrough verified injection, investigation, citation-to-log
  navigation, and five successful recovery requests. Responsive CSS is included;
  a narrow/mobile viewport has not yet been visually verified.
- The Docker app is running at `http://127.0.0.1:8000` and its health check passes.
  Stop it with `docker compose stop app` when finished.

Full evaluation traces are in `artifacts/baseline-test.json`; the measured summary
and limitations are in [docs/BASELINE_RESULTS.md](docs/BASELINE_RESULTS.md).
The test suite emits one upstream Starlette deprecation warning about its httpx
TestClient adapter; it does not affect the passing checks. GitHub Actions is
configured, but has not been exercised on a remote repository.

The host shell blocks local HTTP port binding, so real-HTTP checks and the demo
ran in Docker. Tests do not skip or replace the HTTP lab with fake telemetry.

No live Mistral key is configured in the current environment. Mocked adapter tests
are contract checks, not live API validation or model performance measurements.

## Next work

1. Exercise the live Mistral adapter on smoke cases, then compare all model modes.
2. Add ambiguous symptoms, multi-fault cases, and unseen fault families.
3. Manually review semantic support of findings; automate only defensible checks.
4. Collect feedback from two or three engineers and record resulting changes.
5. Extend the lab toward PostgreSQL/Redis once the first demo is stable.

The first version uses local HTTP and SQLite, as recorded in `docs/DECISION.md`.
It does not yet implement the larger distributed stack proposed in the linked
planning thread. No deployment, customer study, fine-tuning, or production
accuracy claim has been made.
