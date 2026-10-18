# Measuring recovery beyond HTTP 200

On **18 October 2026**, the contract gate rejected **9 incorrect recoveries that
an HTTP-only gate accepted** across 72 paired trials. Both gates scored exactly
the same recorded responses. Separately, the offline policy repaired all 12 fault
episodes; the live Mistral smoke runs each repaired 1 of 4 fault episodes, with
provider failures retained in the denominator.

These are measurements of a small synthetic HTTP/SQLite lab, not production
reliability or evidence of general incident reasoning. The useful result is that
incorrect business outcomes remain visible even when a model or an HTTP-only
check would miss them.

![Actual dashboard showing HTTP error rate zero but five incorrect checkout prices](../assets/semantic-console.png)

## Two questions, two measurements

**Acceptance quality:** each case measures no action, route repair, rollback,
and route-plus-rollback in separate clones of one snapshot. Each trial issues
three requests covering all three products. The evaluator checks both HTTP-only
acceptance and the versioned checkout contract against this same record. This
does not attribute a gain to Mistral or compare different traffic samples.

**Recovery policy:** each policy receives its own lab, may choose up to four
candidate plans of at most two actions each, and must pass five fresh requests
after applying its recommendation. Labels and expected repair actions belong to
the evaluator, not the planner's context. Healthy and missing-telemetry controls
must take no action. Failed provider calls count as failed episodes.

The six scenario families are `silent_price_drift`, `route_and_price_drift`,
`bad_release`, `route_and_release`, `healthy`, and `telemetry_gap`. The test split
uses seeds 11, 23, and 37; smoke uses seed 42. These seeds vary known scenarios;
they are not unseen failure families. Contract version `1.0.0` defines the three
expected prices independently of the running catalog and release.

## Offline test results

| Measurement | Observed result |
| --- | ---: |
| Episodes / paired trials | 18 / 72 |
| Recorded paired probe requests | 216 |
| Completed / unverifiable paired trials | 72 / 0 |
| HTTP-only accepted trials | 39 |
| Contract-accepted trials | 30 |
| False recoveries among HTTP-only acceptances | 9 / 39 (23.08%) |
| Offline adaptive fault recoveries | 12 / 12 |
| Controls taking no action | 6 / 6 |
| Candidate experiments | 18 |
| Provider calls | 0 |

The nine counterexamples are three per seed: silent drift with no repair,
silent drift with an irrelevant route repair, and the masked compound failure
after a route-only repair. In each case all three responses are HTTP 200 and all
three totals exceed the requirement by 100 cents. The contract rejects them.

Lower acceptance is useful here because those nine accepted states are wrong;
it is not evidence that rejecting more plans in general is better. The contract
is itself a declared oracle, so this comparison does not independently establish
that the requirement is correct or complete.

[Measured offline export](results/semantic-offline-results.json) includes the manifest,
environment, timestamps, compact decisions, and counterexamples. Full generated
traces remain in the ignored `artifacts/` directory.

## Live Mistral: successes and failures

Both runs used the pinned **`mistral-small-2603`** model through the Conversations
API, temperature 0, `store: false`, local allowlisted functions, and the same
six-case smoke manifest. No offline policy was substituted on provider failure.
Each run includes four fault cases and two controls.

| Measurement | Initial smoke | Context follow-up |
| --- | ---: | ---: |
| Verified fault recoveries | 1 / 4 | 1 / 4 |
| Controls taking no action | 2 / 2 | 2 / 2 |
| Episode errors | 2 | 3 |
| Recorded provider attempts | 6 | 7 |
| Reported input tokens | 24,229 | 28,951 |
| Reported output tokens | 769 | 870 |
| Recorded candidate experiments | 3 | 4 |

In both runs Mistral correctly selected a rollback for the standalone silent
price drift, and the result passed fresh contract verification. Neither run
recovered a compound case. The controls required no model calls.

In the initial run, Mistral repaired the route, saw HTTP 200 with incorrect
prices, then requested a rollback alone. Since every experiment resets to the
original snapshot, that omitted the route repair and returned 502 again. The
model abstained. Two later episodes had provider errors; the adapter at that
point did not retain safe status metadata, so their exact causes are unknown.

The follow-up added explicit full-plan execution semantics, action differences
between trials, and safe provider failure categories. Mistral then tried the
catalog-path action for the price mismatch and eventually combined it with the
route repair. Prices still failed. Its next call and the subsequent two fault
episodes returned **HTTP 429**. All three errors remain in the denominator.
The provider supplied no usable numeric Retry-After value. No automatic retries
were made, and no further live benchmark was run after this follow-up.

This follow-up exposed a rate limit; it **did not demonstrate an improvement in
model recovery quality**. Both traces also show the value of the external gate:
neither incomplete HTTP-200 repair received promotion authority. The prompt and
tool-effect descriptions still need evaluation on a wider case set and across
models before a stronger live-model claim is justified.

See the [initial live export](results/semantic-mistral-initial-results.json) and
[follow-up export](results/semantic-mistral-followup-results.json). Token totals cover
reported responses only; failed requests may have unobserved usage. Dollar cost
is unknown because prices were not configured. The table is not a billing
ledger, and these two runs are not independent estimates of general accuracy.

## Integration debugging retained outside the benchmark

Before these suites, the Conversations endpoint rejected the old
`tool_choice: "any"` with HTTP 422. A diagnostic request confirmed that this
endpoint accepts `auto`, `none`, or `required`; the adapter now uses `required`.
A corrected pilot on `route_and_release` made three model calls, selected an
incomplete repair, and abstained. It recorded 15,507 input and 437 output tokens
without a recovery. Tool-effect descriptions were added afterward. These setup
attempts are not silently counted as successful benchmark cases or removed from
the engineering narrative; their original local artifacts are retained.

## Reproduce

Offline, with no credential or paid request:

```sh
docker compose --profile eval run --build --rm eval \
  incidentlab-semantic-eval --split test --strategies adaptive \
  --output artifacts/semantic-offline-test.json
```

For a deliberate paid smoke run, configure the ignored `.env` first:

```sh
docker compose --profile eval run --build --rm \
  -e MISTRAL_MODEL=mistral-small-2603 eval \
  incidentlab-semantic-eval --split smoke --strategies adaptive,mistral \
  --allow-paid-api --output artifacts/semantic-mistral-smoke.json
```

The CLI saves its report even when a comparison arm fails, then exits nonzero.
Keep the failed artifact. Model availability, provider limits, nondeterminism,
and future prompt changes can change the outcome. The two published live
exports intentionally preserve both implementation iterations.

[Contract design](../architecture/SEMANTIC_RECOVERY.md) · [FDE case study](../career/MISTRAL_FDE.md) ·
[Project overview](../../README.md)
