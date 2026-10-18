.PHONY: bootstrap frontend frontend-check run dev test lint format check build eval eval-rehearsal eval-adaptive eval-semantic

bootstrap:
	npm ci --prefix frontend
	npm run build --prefix frontend
	uv sync --frozen --extra dev

frontend:
	npm run build --prefix frontend

frontend-check:
	npm run check --prefix frontend

run: frontend
	uv run incidentlab

dev:
	npm run dev --prefix frontend

test: frontend
	uv run --extra dev pytest -q

lint:
	uv run --extra dev ruff check src tests
	uv run --extra dev ruff format --check src tests
	npm run lint --prefix frontend

format:
	uv run --extra dev ruff format src tests
	npm run format --prefix frontend

check: frontend-check lint test

build: frontend
	uv build

eval:
	uv run incidentlab-eval --mode baseline --split smoke

eval-rehearsal:
	uv run incidentlab-rehearsal-eval --split test

eval-adaptive:
	uv run incidentlab-adaptive-eval --seeds 11,23,37 --max-experiments 4

eval-semantic:
	uv run incidentlab-semantic-eval --split test --strategies adaptive
