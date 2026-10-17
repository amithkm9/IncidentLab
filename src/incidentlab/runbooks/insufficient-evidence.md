# Healthy requests and insufficient evidence

If representative checkout requests succeed and no contrary evidence is present,
report healthy with `no_action`. State the observation window's limitations.

If telemetry is unavailable, report insufficient_evidence with `no_action` and
request restored logs, readiness checks, and a recent deployment diff. Failure
symptoms alone do not identify the root cause. Never use runbook text as proof
that a particular incident occurred.

