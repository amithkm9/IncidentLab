# Codebase quality and security review

Started 2026-10-18 after the TypeScript migration. Items are checked only after
their evidence is recorded. The prior migration checklist remains historical.

## Ordered checklist

1. [x] Identify remaining warnings in build, application, CI, and available editor diagnostics; fix reproduced causes.
2. [x] Review every source area for correctness, dead code, and maintainability; record findings and remove confirmed unused code.
3. [x] Organize backend packages, frontend modules/styles, tests, and documentation with consistent names; update imports and packaging.
4. [x] Review tracked and generated files; remove obsolete project files while preserving credentials, user data, and measured evidence.
5. [x] Make the README a public entry point with navigation, diagrams, setup, workflow, results, structure, and security boundaries.
6. [x] Use the requested security extension where available; review trust boundaries and dependencies locally; fix and test confirmed findings.
7. [x] Validate local builds, tests, packaging, documentation references, and security checks.
8. [ ] Push reviewed commits and verify hosted CI.

## Findings and evidence

- Remaining reproduced build warning: Docker installed `uv` with root `pip`.
  The image now copies the same pinned `uv:0.9.5` binary from Astral's image.
  The rebuilt test image completed without that warning. npm update notices are
  informational; they do not justify unrelated dependency upgrades.
- Backend packages now separate API/security, domain contracts, the HTTP lab,
  investigation, recovery, evaluation, application coordination, and storage.
  Tests mirror these responsibilities. Frontend HTTP validation/path helpers and
  ordered feature styles have dedicated directories.
- Consolidated the demo guide into README, renamed topic docs to lowercase
  kebab-case, and removed three unreferenced SVGs. Recorded evaluation JSON is
  unchanged. Runtime data, credentials, and useful historical evidence remain.
- README has navigation, two Mermaid diagrams validated with the Mermaid parser,
  complete setup/demo instructions, evidence denominators, and security scope.
- npm audit: zero known advisories across the locked frontend dependency tree.
  pip-audit: zero known advisories in the hashed lockfile export including dev.
  This is a point-in-time advisory check, not proof that dependencies are secure.
- Codex Security Cloud was opened and availability checked. No Cloud environment
  is configured and the interactive app is unavailable in this session. No cloud
  scan ran and no cloud findings are claimed. Local security work continues.
- Bandit: three URL-opening review flags and one deterministic-randomness flag.
  URLs are produced by the disposable lab or its internal configuration; API and
  model tools cannot supply arbitrary endpoints. Seeded randomness chooses test
  traffic, not credentials or authorization tokens. No rule suppression added.
- Vulture at 90% confidence found only six pytest fixture arguments used for their
  environment-setup side effects; these are not dead code. Ruff found no unused
  production imports. The TypeScript compiler API found zero unused runtime
  exports/files and zero runtime import cycles across 25 modules. Used type
  declarations and pytest fixtures were retained. Local integration passed; hosted CI is pending.

The exact warning reported by the user remains unspecified. Browser/editor
warnings beyond the reproduced build output are not assumed to be the same issue.

## Scope

Review the local IncidentLab repository and its authorized GitHub remote.
Do not make paid model calls or scan unrelated systems. Local experiments are
disposable; existing incident history and recorded evaluation artifacts remain
useful project evidence. Cloud scan access or authentication requirements will
be reported separately from completed local checks.

## Security findings fixed

| Boundary | Reproduced issue | Change and regression coverage |
| --- | --- | --- |
| Browser → local API | An arbitrary Host with matching Origin reached a mutation; malformed Origin could return 500 | Explicit loopback host allowlist, strict scheme/host/port comparison, duplicate-header rejection, and Fetch Metadata checks |
| Request/response | Unbounded body reads, cacheable API responses, arbitrary exception text | 64 KiB/10-second body limits, API `no-store`, security headers, sanitized errors with validated numeric provider statuses |
| Saved records | Truthy string flags fabricated recovery history; malformed/deep JSON or broken stored records crashed readers | Exact booleans, bounded regular-file imports, schema validation, tolerant history reads; rejected legacy records cannot create recovery events |
| Markdown exports | Stored metadata could inject Markdown structure | Escape untrusted content before export |
| Browser state | Unchecked response objects replaced valid state; refresh failures left old controls enabled | Runtime shape checks before state updates, encoded/validated artifact IDs, and mutation lock until refresh succeeds |

The API/model interface exposes no arbitrary shell, SQL, URL, or filesystem
operation. Provider calls use fixed Mistral HTTPS endpoints; SQL data is bound
through parameters; model tools are read-only and remediation actions are enums.
Current in-memory episode/revision/fingerprint checks, not archived rows, grant
mutation authority. These conclusions apply to this local demo's interfaces.

Limits: there is no authentication or tenant isolation. Observation lists and
persisted history do not have a global retention limit; per-operation budgets do
not bound lifetime memory/disk consumption. A signed audit trail, public hosting,
production telemetry ingestion, and cloud security scan are outside the completed
local review. No paid model calls or credential changes were made.

Tools: npm audit; pip-audit 2.10.1; Bandit 1.9.4; Vulture 2.16; TypeScript compiler
analysis; Ruff; Codex Security Cloud availability checks. The Cloud extension had
no configured environment, so its result must not be presented as a completed scan.

## Final local validation

- Backend: **345 tests**, warnings treated as errors; Ruff lint/format pass.
- Frontend: strict TypeScript, ESLint, Prettier, **47 tests**, production build;
  **21/21** real offline API responses accepted, including proof and promotion.
- Four evaluation CLIs passed smoke runs with zero provider calls. Known-scenario
  counts match the previous run; no benchmark improvement is inferred.
- Docker app/test images build without warnings; the rebuilt app is healthy.
- Wheel and source archive builds pass. The extracted wheel serves four referenced
  assets, loads six runbooks and four evaluation modules, and enforces API headers
  and Host validation independently of the source checkout.
- Safari: demo → adaptive rehearsal → 36-response proof → promotion; five fresh
  HTTP/price/SKU checks pass, and proof becomes historical/read-only. Desktop
  layout was visually checked. No new comprehensive accessibility/mobile audit.
- Mermaid diagrams pass the real Mermaid parser. Local links and anchors were
  checked, including Linux-sensitive filename case. Six published JSON artifacts
  are unchanged; an exact-key scan found no credential in publishable source,
  frontend output, wheel, or source archive.

The exact warning originally seen by the user was not supplied; the Docker/pip
warning above is the one reproduced and fixed during this review.
