# Development workflow

Use Python 3.11+, Node.js 24+ with npm, and
[uv](https://docs.astral.sh/uv/). Docker Compose provides the complete alternative
when the host cannot bind the lab's loopback HTTP ports.

## Bootstrap and run

From the repository root:

```sh
make bootstrap
uv run incidentlab
```

Bootstrap runs `npm ci --prefix frontend`, `npm run build --prefix frontend`,
then `uv sync --frozen --extra dev`. Both dependency lockfiles are tracked. The
frontend build must exist before Python installation because the package ships
the same built UI. Open <http://127.0.0.1:8000>; one app process owns one lab.

For frontend iteration, keep that backend running and start a second terminal:

```sh
npm run dev --prefix frontend
```

Vite serves the TypeScript application and proxies API calls to the local
backend. After changing source, `make run` rebuilds the production UI and starts
FastAPI. Generated `frontend/dist/`, `node_modules/`, Python environments, local
runtime data, and full experiment output remain outside version control.

## Check a change

The combined check is `make check`. To run its components and the formatting
check separately:

```sh
uv run --extra dev ruff check src tests
uv run --extra dev ruff format --check src tests
npm run typecheck --prefix frontend
npm run lint --prefix frontend
npm run test --prefix frontend
npm run build --prefix frontend
uv run --extra dev pytest -q
```

Ruff checks imports and Python errors using the repository's Python 3.11 target.
TypeScript checks the frontend before Vite builds it. Tests are grouped into
`tests/domain/`, `tests/lab/`, `tests/investigation/`, `tests/recovery/`, `tests/api/`, and `tests/evaluation/`; API and lab tests use real
local HTTP services where appropriate. Storage tests live in `tests/test_storage.py`;
shared fixtures are in `tests/conftest.py`. Provider contract tests use mocks and
make no paid calls. Pytest treats warnings as errors so dependency regressions
remain visible.

If the host restricts loopback binding, run the backend suite in Docker:

```sh
docker compose --profile test run --build --rm test
```

Formatting is an explicit operation (`make format`); check and build commands
do not rewrite source. Follow the [work plan](implementation-plan.md) for
the completed migration and the [codebase audit](codebase-audit.md) for the current review and the [evaluation protocols](../README.md)
for benchmark commands and interpretation.

## Why two HTTP client packages?

The runtime Mistral adapters use `httpx`. The resolved Starlette version uses
`httpx2` for its TestClient and warns when falling back to legacy `httpx`.
The development extra therefore includes `httpx2`; both clients can coexist.
This fixes the deprecated path without hiding warnings or changing the provider
integration. See the official [Starlette TestClient documentation](https://starlette.dev/testclient/)
and FastAPI's [matching test-dependency change](https://github.com/fastapi/fastapi/pull/15603).

The migration was checked against local FastAPI 0.143.3 / Starlette 1.8.0 and
the locked `httpx2` 2.13.1 release. A fresh Python process with `-W error`
imported TestClient, confirmed the `httpx2` adapter, and completed an in-process
request. This check does not replace the real-HTTP integration suite.

## Troubleshooting setup

| Symptom | Action |
| --- | --- |
| Hatch reports `Forced include not found: .../frontend/dist` | Run `make bootstrap`; the UI must build before Python installation. |
| Starlette warns about the deprecated `httpx` TestClient adapter | Run `uv sync --frozen --extra dev` after the frontend build; ensure pytest uses this repository's `.venv`. Do not add a warning filter. |
| Frontend changes do not appear at port 8000 | Run `make frontend`; port 8000 serves production output. Use `make dev` and the Vite URL for source iteration. |
| Vite API calls fail | Start the backend separately with `uv run incidentlab`; its default proxy target is port 8000. |
| Port 8000 is occupied | Stop the previous app or use `uv run incidentlab --port 8001`; update the Vite proxy if using a different backend port. |
| Tests cannot bind loopback ports | Run the Docker test service; the lab intentionally uses real HTTP servers. |

For a single-command application startup without local Python or Node setup,
run `docker compose up --build -d app` and open <http://127.0.0.1:8000>.

## Package the same frontend

```sh
make build
```

Vite writes `frontend/dist/`. Hatch includes it as `incidentlab/web` in a wheel
and retains `frontend/dist/` in the source distribution so a wheel can be rebuilt
without rerunning npm. The source checkout serves the generated distribution;
an installed package serves its bundled copy. Missing frontend output fails the
package build instead of producing an empty UI. This uses Hatch's documented
[forced-inclusion mapping](https://hatch.pypa.io/latest/config/build/#forced-inclusion).

The Docker build also compiles the frontend before installing the backend. No
frontend development server or external CDN is needed to run the packaged app.
Keep API credentials in the server environment or ignored local `.env` used by
Compose; the Python CLI does not load that file automatically.

## Hosted CI runtime

The workflow pins `ubuntu-24.04` and uses `actions/checkout@v7` and
`actions/upload-artifact@v7`. Both action definitions declare Node 24:
[checkout](https://github.com/actions/checkout/blob/v7/action.yml) and
[artifact upload](https://github.com/actions/upload-artifact/blob/v7/action.yml).
This resolves the deprecated Node 20 action warning. Pinning the runner avoids
GitHub's announced [Ubuntu-latest migration](https://github.com/actions/runner-images/issues/14748)
changing the host image implicitly. Repository permissions are read-only, and
checkout credentials are not retained after fetching source.

## Container tool installation

The image copies the pinned `uv` binary from Astral’s official container image,
following its [Docker integration guide](https://docs.astral.sh/uv/guides/integration/docker/).
This removes the root-user `pip install uv` warning at its source. Application
execution still uses the unprivileged `lab` user.
