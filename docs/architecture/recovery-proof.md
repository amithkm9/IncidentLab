# Recovery Proof: measure what each fix contributes

Recovery Proof replays a recommended plan and removes one action at a time.
It tests whether those actions were needed for this snapshot's sampled checkout
contract. The feature makes **zero model calls**, leaves the active lab unchanged,
and issues **at most 36 checkout requests** per proof run.

![Illustrated route and price-drift case: all experiments start from one snapshot; the full plan passes while the no-change control and each action removal fail, followed by current-state checks and operator approval](../assets/recovery-proof.svg)

The illustration describes the guided scenario's expected mechanism. Inspect
the actual proof's recorded trials before drawing a conclusion; the diagram is
not a benchmark result.

## Recorded guided run

The [saved route-and-price proof](../evaluation/results/recovery-proof-route-price.json)
completed four trials and **36 checkout responses**, with zero provider calls
and the source unchanged. The full plan passed all nine HTTP and contract checks.
The control and the variant without the route fix each returned nine HTTP 502s.
Without rollback, all nine responses returned HTTP 200 but failed the price
contract. Both actions were therefore necessary within this measured plan.

The artifact's unsigned digest was verified after export. This is one controlled
local run, not a population-level recovery result. Its saved eligibility fields
describe that measurement; the file does not establish current promotion authority.

## What runs

The service accepts only the current rehearsal's passing recommendation, while
its source fingerprint, episode, revision, and business contract still match.
A failing rehearsal control and available diagnostic telemetry are required.
It snapshots that state once, then measures independent HTTP/SQLite clones:

| Trial | Applied actions | Question |
| --- | --- | --- |
| No-action control | None | Does the original incident still fail? |
| Full plan | Every recommended action | Does the recommended repair hold up under fresh checks? |
| Leave one action out | Full plan minus one action, repeated for each action | Does removing this action make the sampled contract fail? |

Two-action plans need four trials. A one-action plan needs only two because
its removal trial is already the no-action control. Every trial sends nine
requests, covering notebook, lamp, and mug three times each. That is **18 planned
requests for one action** or **36 for two actions**. Fixes never carry between
trials. Promotion's five fresh requests are separate from this proof budget.

The engine checks complete response/status lists, contract identity, product
coverage, expected totals, observed values, and consistency of outcome flags.
It stops on an incomplete or contradictory measurement or execution error.
Budget fields distinguish planned, started, and completed trials. Completed-trial
request totals exclude partial traffic from a failed trial; such traffic remains
within the overall 36-request ceiling.

## Read the conclusion correctly

| Conclusion | Evidence | Effect on this rehearsal's promotion |
| --- | --- | --- |
| `supported` | Full plan passes; control and every action removal fail | Eligible if current-state and integrity checks also pass |
| `redundant_action` | Full plan passes and control fails, but at least one action removal also passes | Still eligible; the evidence does not establish necessity of every action |
| `full_plan_failed` | The full plan fails fresh verification | Blocked |
| `control_healthy` | The unchanged source already passes | Blocked |
| `inconclusive` | Required measurements did not complete validly | Blocked |

“Necessary” means that removing this action from this particular passing plan
caused a measured failure. It does not establish a globally minimal plan, a
unique root cause, correctness of undeclared business rules, or production
safety. A redundant action is reported honestly; the engine does not silently
replace the recommended plan with another plan.

## Evidence is separate from current authority

The JSON artifact records its plan and rehearsal IDs, source fingerprint,
episode/revision, contract, actions, per-request checks, necessity conclusions,
budget, timing, errors, and limitations. Repeated proofs retain prior artifacts
in the rehearsal's proof history. The service checks that the source is unchanged
after measurement and records the outcome in SQLite history and audit events.

Its SHA-256 digest covers canonical UTF-8 JSON of the **proof object**, excluding
the `digest` field. It is **unsigned**. Comparison with a trusted digest can
detect changed content; anyone who can replace both content and digest can
recompute it. The digest authenticates neither an author nor the claims.

The API returns `{ "proof": ..., "authority": ... }`. `authority` is recomputed
against the running lab and is outside the proof digest. A valid old artifact
may therefore remain readable while `authority.is_current` is false. Promotion
also requires the current unpromoted rehearsal, matching plan/actions,
episode/revision, source fingerprint and contract, intact proof content, and a
promotion-eligible result.

Proof is an **optional additional check**. Once a proof exists for a rehearsal,
its failed, incomplete, stale, or altered result cannot be bypassed by promoting
that rehearsal. A later failed proof attempt also blocks an older passing proof.
Run a successful current proof or a new rehearsal to proceed. Explicit operator
promotion still applies the selected plan and checks five new active-lab
responses; the proof does not perform that mutation.

## Try it and export the record

1. Follow the [silent-failure demo](../../README.md#try-the-demo) through a passing combined
   recommendation.
2. Select **Explain why each fix is needed**. Compare the full-plan, no-change,
   and action-removal cards, including HTTP success with a failed price check.
3. Read the necessity statements, scope, current-state status, and budget. Use
   **Download recovery proof JSON** to retain the artifact and current authority.
4. Promote only after reviewing the evidence; inspect the five fresh final checks.

`POST /api/rehearsals/{rehearsal_id}/proof` measures the current recommendation.
`GET` on the same path exports its saved proof and recomputed authority.
Historical records remain inspectable; they cannot authorize changes in another
episode or after promotion.

Implementation: [proof engine](../../src/incidentlab/recovery/proof.py),
[service authority and persistence](../../src/incidentlab/application.py),
[API](../../src/incidentlab/api/app.py). See also
[semantic contracts](semantic-recovery.md) and [architecture](overview.md).
