.PHONY: run test eval eval-rehearsal
run:
	uv run incidentlab
test:
	uv run --extra dev pytest -q
eval:
	uv run incidentlab-eval --mode baseline --split smoke
eval-rehearsal:
	uv run incidentlab-rehearsal-eval --split test
