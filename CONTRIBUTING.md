# Contributing to IncidentLab

Start with the [development guide](docs/development/README.md) and
[architecture](docs/architecture/ARCHITECTURE.md). Keep each change focused on a
concrete behavior, with evidence that it works and clear limits on what it proves.

## Setup and checks

Install Python 3.11+, Node.js 24+ with npm, and uv, then run:

```sh
make bootstrap
make check
```

`make bootstrap` installs locked frontend packages, builds the frontend, and
installs the locked Python development environment. `make check` runs frontend
checks, Python lint, and backend tests. Backend tests need loopback HTTP ports;
use the [Docker test command](docs/development/README.md#check-a-change) if your
host blocks those ports. `make build` produces the frontend and Python
distributions. `make format` deliberately rewrites formatting; review its diff.

## Edit source, preserve evidence

| Area | Edit | Generated output |
| --- | --- | --- |
| Frontend | `frontend/src/`, `frontend/index.html`, `frontend/public/` | Vite writes `frontend/dist/`; do not edit it manually |
| Backend | `src/incidentlab/` | Python wheels bundle the built UI at `incidentlab/web` |
| Evaluators | `src/incidentlab/evaluation/` and its manifests | New full runs write to ignored `artifacts/` |
| Tests | `tests/core/`, `tests/api/`, `tests/evaluation/`, frontend tests beside their modules | Test caches and coverage remain untracked |
| Documentation | The relevant category under `docs/` | Keep relative links valid after moves |

Update dependency declarations and their lockfiles together. Use strict
TypeScript types at the API/UI boundary and validate untrusted payloads where
they enter the system. Keep evaluation labels and expected answers outside
planner observations. Apply narrowly scoped fixes to warnings rather than
silencing them; the Python suite treats warnings as errors.

Add or update tests for meaningful behavior changes, especially contract
validation, stale-state rejection, provider failure, and experiment accounting.
Mock provider calls in automated tests. Live model evaluations require deliberate
cost opt-in and server-side credentials; never commit `.env` or credential data.

Keep unsuccessful evaluation cases in denominators and preserve historical
results with their original protocol and recovery definition. Do not relabel
offline policy results as model quality or controlled lab results as production
performance. Record relevant commands, outcomes, and limitations in your change
description. A reviewer should be able to reproduce the result without reading
the development conversation.
