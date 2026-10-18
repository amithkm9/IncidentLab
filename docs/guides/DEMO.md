# IncidentLab demo: available does not always mean correct

Run `docker compose up --build -d app` and open <http://127.0.0.1:8000>.
This walkthrough uses the offline policy and makes no model API calls.

![An isolated route repair returns HTTP 200 with the wrong price; a combined repair must pass the independent contract](../assets/semantic-recovery.svg)

1. Choose **Try the silent-failure demo**. It injects
   `route_and_price_drift` at seed 42, runs the first offline investigation, and
   selects adaptive rehearsal with a four-experiment ceiling and two-action limit.
2. Inspect the diagnosis and open a citation. Checkout returns HTTP 502 because
   its inventory request reaches a nonexistent route; the underlying HTTP 404
   appears in the evidence.
3. Open **Fix rehearsal** and run **Adaptive · offline policy**. The control
   and every candidate use isolated HTTP services and a SQLite copy. The active
   incident stays unchanged.
4. Inspect the route-only trial. HTTP requests now return 200, but the pricing
   release adds $1.00 to each total: a notebook returns $13.00 against the
   independent contract's $12.00 requirement. Open the business checks and read
   the expected and observed values. This trial is a failed recovery.
5. Follow the adaptive decision trail. The measured `price_mismatch` supports
   a new plan combining route restoration and release rollback. Every trial
   starts from the original snapshot, so the next plan must include the route
   repair again. Both HTTP and contract checks pass for the combined plan.
6. Select **Explain why each fix is needed**. Recovery Proof replays the full
   plan, the unchanged control, and each action removal in fresh isolated
   copies. Each trial checks all three products three times, up to 36 requests
   and zero model calls. Inspect whether removing the route fix breaks HTTP,
   while removing rollback returns HTTP 200 with incorrect prices. Use the
   actual trial results to assess necessity within this plan.
7. Select **Apply plan & verify**. The server checks that the episode, revision,
   state, and contract still match the tested snapshot. Five fresh requests in
   the active lab must pass availability and business-contract verification.
8. Download the proof JSON, experiment JSON, and incident report. Inspect the expected totals,
   returned product IDs, contract version/hash, decision evidence, and final
   verification. Open history to revisit the saved record.

The three-product contract covers notebook, lamp, and mug. Default three-request
trials and five-request verification cycle through all three; the notebook
amount above is one concrete example.

Recovery Proof is optional, but an existing failed or incomplete proof blocks
promotion of that rehearsal. Its unsigned content digest is separate from
current permission to mutate the lab. A passing proof supports the measured
plan; it does not establish a globally minimal repair or production safety.
[Read the proof protocol and limits](../architecture/RECOVERY_PROOF.md).

## Show why the budget matters

Start the demo again. Set **Experiment budget** to **1** and run the adaptive
policy. The route repair returns HTTP 200 with incorrect totals; no passing
plan can be promoted. Increase the ceiling to **4** and rerun against the
unchanged active state. The offline policy can test the combined repair after
observing the first trial's price mismatch.

For a broader comparison, select **Compare all plans**. Inspect the no-change
control, each single fix, and the action pairs. Use **Show → Passed** to isolate
passing plans, then return to **All outcomes** to retain the failed evidence.

## Check the controls and the live-model boundary

Repeat with **Healthy control** and **Missing evidence**. Both should offer no
recommended mutation. A healthy response must satisfy the contract; unavailable
diagnostic evidence requires abstention. Restarting the app preserves history
but creates a new lab episode, so older plans remain read-only.

**Adaptive · Mistral agent** uses the same experiment and approval boundaries,
with the live model selecting plans. Its decisions may differ from the offline
reference. The first pinned live smoke exposed provider errors and a compound
plan that omitted a required prior repair; the recorded result is **1/4 fault
recoveries**, not a promised successful demo. See the retained evaluation
before presenting model quality.

[Contract details](../architecture/SEMANTIC_RECOVERY.md) ·
[Current semantic evaluation](../evaluation/SEMANTIC_EVALUATION.md) ·
[Mistral integration and customer-pilot plan](../career/MISTRAL_FDE.md)

The demonstration establishes declared requirements in a local lab. It does not
establish production rollout safety, long-term reliability, or a reduction in
real incident resolution time.
