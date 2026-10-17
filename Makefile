.PHONY: run test eval
run:
	uv run incidentlab
test:
	uv run --extra dev pytest -q
eval:
	uv run incidentlab-eval --mode baseline --split smoke
