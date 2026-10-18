# IncidentLab frontend

The recovery workbench is a Vite application written in strict TypeScript and native DOM APIs. It runs against the local IncidentLab API; no data or successful outcomes are simulated in the browser.

Use Node.js 24, matching the container build:

```sh
cd frontend
npm ci
npm run check
npm run build
```

`check` runs TypeScript, ESLint, formatting checks, and Vitest. `npm run format` applies Prettier. Tests cover the HTTP-versus-business recovery distinction, legacy observations, safe provider diagnostics, snapshot and proof guards, and failed HTTP requests.

For development, start the Python API on port 8000, then run `npm run dev`. Vite proxies `/api`, `/healthz`, `/docs`, and `/openapi.json` to the backend. The API proxy preserves the browser Host so same-origin mutation checks remain enforced. Production serves the built UI and API from one origin.

## Structure

- `src/domain.ts` describes API and saved-artifact contracts, including nullable proof outcomes and older reports without business checks.
- `src/api.ts` contains the typed HTTP client and actionable transport errors. Response types document the backend contract; they are not runtime schema validation.
- `src/dom.ts` ties static element IDs to their HTML types and centralizes safe text-based DOM construction.
- `src/state.ts`, `controller.ts`, `navigation.ts`, and `main.ts` handle workspace state, operations, navigation, and event wiring.
- `src/views/` renders the workbench, investigation, contracts, experiments, proof, and history.
- `src/verification.ts` and `recovery.ts` hold pure observation and permission logic.
- `src/style.css` contains design tokens, components, and responsive rules.

`npm run build` emits `dist/index.html`, hashed JS/CSS in `dist/static/assets/`, and SVGs in `dist/static/`. The backend serves `/` from the index and mounts `/static` from that directory. Generated assets are not source files. Docker builds them before packaging the Python application.

Recovery Proof is an explicit, optional isolated experiment. It tests the full plan and variants with one action removed, then displays actual HTTP and business-contract observations. Archived proof is read-only. Failed or stale proof blocks promotion in the UI and backend; the backend remains the authority for applying a plan.
