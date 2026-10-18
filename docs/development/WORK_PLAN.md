# TypeScript, repository quality, and Recovery Proof

Requested 2026-10-18. This checklist tracks the current implementation pass.

## Delivery checklist

- [x] Migrate all handwritten frontend JavaScript to strict TypeScript.
- [x] Split frontend responsibilities into domain types, API access, UI modules, and styles.
- [x] Add reproducible frontend install, typecheck, lint, tests, and production build commands.
- [x] Serve the built frontend in local development, the Python package, and Docker.
- [x] Group evaluation runners, tests, guides, architecture notes, and result artifacts consistently.
- [x] Update imports, packaging, documentation links, and CI for the new structure.
- [x] Remove migrated source, verified unused code, and unnecessary generated/tracked files.
- [x] Diagnose the reported warning and fix its cause; preserve useful diagnostics.
- [x] Implement counterfactual Recovery Proof with bounded, isolated experiments.
- [x] Expose proof evidence and exports in the TypeScript interface.
- [x] Reject stale proofs and prevent a failed proof from authorizing promotion.
- [x] Run backend tests, frontend checks, representative benchmarks, and browser walkthroughs.
- [x] Record measured results and remaining limitations.
- [x] Commit meaningful changes and push the verified result.

## Ownership and scope

The frontend agent owns `frontend/`. The backend agent owns the proof engine and
its API/service integration. The quality agent owns dependency-warning research,
Python tooling configuration, and documentation organization. The coordinating
agent owns build/container integration, evaluation/test organization, final
verification, and this checklist.

Recovery Proof measures the full repair, no-action control, and each repair with
one action removed. Each trial uses a fresh clone of the same snapshot and
checks HTTP responses against the independent checkout contract. This can show
that an action is necessary within the measured plan and sample; it cannot
establish global minimality, production safety, or first-ever novelty. It makes
no model API calls.

Existing incident history, failed live-model results, and reproducibility
artifacts remain useful evidence. Remove a source file only after its replacement
works or references and behavior establish that it is unused. Credentials remain
outside version control.

## Verification record

- Strict TypeScript, ESLint, Prettier, 21 frontend tests, and production build pass.
- Docker backend: 278 tests pass with warnings treated as errors; Ruff lint and formatting pass.
- Both the deprecated TestClient adapter and unclosed HTTP error responses are fixed.
- All four evaluation CLI smoke commands pass without model calls.
- Wheel/sdist include built assets; legacy frontend and obsolete screenshots are removed.
- Safari demo → rehearsal → 36-response proof → promotion verifies five fresh requests.
- Desktop proof and 390 × 844 mobile workbench spot checks pass; this is not a full device audit.
- Measured proof is retained in `docs/evaluation/results/recovery-proof-route-price.json`.
- Existing live-model limitations and unsuccessful provider results remain documented.
