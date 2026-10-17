# IncidentLab demo: a fix that reveals another failure

Run `docker compose up --build -d app` and open <http://127.0.0.1:8000>.
Use the offline baseline; this walkthrough makes no model API calls.

For a quick start, choose **Start guided demo**. It creates the compound incident
at seed 42 and runs its first offline investigation. Continue at step 2 to inspect
the evidence, then rehearse and apply a plan yourself.

1. Select **Route drift masks a pricing regression**, seed 42, and start it.
   Checkout fails because it calls an inventory route that does not exist.
2. Run the investigation. Open a citation and inspect the actual HTTP 404
   observation. The proposed route repair is supported, but is only one action.
3. Optional demonstration: apply that single fix. Checkout now reaches pricing
   and returns HTTP 500. The initial diagnosis did not establish full recovery.
   Re-inject the compound scenario to compare the complete original state.
4. Open **Fix rehearsal** and run the two-action comparison. The active lab does
   not change. Each of 15 plans and the no-change control gets separate local
   HTTP services and a SQLite database copied from the current state.
5. Inspect control, route-only, rollback-only, and the combined plan. Only the
   combined route repair plus pricing rollback restores this incident. Selection
   uses measured responses and plan size, not the scenario's expected answer.
   Use **Show → Passed** to isolate the successful plan; **All outcomes** restores
   the control and failed experiments.
6. Promote the recommended plan. Five new requests run against the active lab.
   The result must explicitly say recovery verified; rehearsal success alone is
   not counted as active-lab recovery.
7. Export the experiment JSON and incident report. Open history, reload the
   workspace, and inspect the persistent evidence and timeline.

Follow with healthy and missing-evidence controls. Both should produce no
recommended change. Restarting the app preserves history but creates a new lab
episode; old plans remain read-only.

The portfolio result is expanded recovery capability on known compound faults,
with isolation, provenance, and guarded promotion. It is not a claim that an LLM
invented a fix, that the experiment budget is equal to the one-shot comparator,
or that the result transfers to production infrastructure.
