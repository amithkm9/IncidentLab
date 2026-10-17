# Evaluation protocol

The goal is to measure whether an investigation identifies the injected fault
and whether its proposed lab action restores checkout. This is a controlled
engineering benchmark, not a production reliability estimate.

## Frozen cases

`src/incidentlab/benchmark.json` defines case identities before model evaluation:

- Smoke: 7 scenario families × 1 seed = 7 episodes.
- Development: 7 families × 3 seeds = 21 episodes.
- Test: 7 families × 15 seeds = 105 episodes.

Development and test seeds are disjoint. All splits reuse the same fault
families. Seeds vary product request order and three client-timeout/dependency
delay settings. Many cases are otherwise identical. Do not report these as
105 independent faults, novel test families, or statistical evidence of
generalization. Once a test case informs a code change, record that fact before
making any held-out evaluation claim.

The five actionable cases are wrong inventory route, unavailable inventory,
short client deadline, unavailable catalog, and a pricing regression. Controls
cover healthy checkout and unavailable diagnostic telemetry. The scenario
registry contains expected labels for the evaluator; those labels are not in
the investigator's tool context.

## Per-episode protocol

1. Reset the lab, apply the case's fault and seed, and issue four checkout requests.
2. Run exactly one selected investigation mode. Capture every observed tool
   result and the validated finding. Errors count as failed episodes.
3. Compare the predicted cause and action against the case's ground truth.
4. If the investigator proposes an executable action, apply it in the disposable
   lab and issue five fresh checkout requests. Recovery requires five HTTP 200s.
5. Save the result, errors, traces, before-state, and recovery responses.

The evaluation runner's command explicitly authorizes these lab-only fixes. The
interactive app requires an explicit operator click instead. A wrong proposed
fix can fail verification; the evaluator does not substitute the expected fix.

## Metrics and denominators

| Metric | Definition |
| --- | --- |
| Diagnosis accuracy | Correct cause / all attempted episodes, including errors |
| Action accuracy | Correct allowlisted action / all attempted episodes |
| Remediation success | Verified recoveries / episodes with an actionable ground-truth fault |
| Appropriate abstention | Insufficient-evidence diagnosis plus no action / missing-telemetry cases |
| Control no-action rate | Correct no-action finding / healthy and missing-telemetry cases |
| Median/p95 latency | Investigator time on completed findings; excludes injection and recovery |
| Tokens | Provider-reported tokens on completed findings |
| Estimated cost | Configured prices × recorded tokens; unknown if prices are absent or any episode errors |

Failed or malformed API responses may still incur charges. Reported token totals
cover completed findings and are not a billing ledger. Errors remain in the
quality denominators. API failures are never converted into baseline findings.

Citation validation checks that references exist and non-abstaining findings
cite observed incident evidence. **Semantic evidence support is not measured
automatically.** Review claims against the saved evidence before reporting an
unsupported-conclusion rate. Health endpoints and runbooks alone are weak
support for root-cause claims.

## Comparing modes

Use the same manifest, split, model version, pricing assumptions, and code for
`prompt`, `retrieval`, and `mistral`. Each sees the same kind of initial log and
metric snapshot; tool mode may gather additional observations. Timings are live
and cannot be byte-identical between runs. Save provider version IDs when
available; a `-latest` alias is not a pinned model. Report baseline separately.

Keep the full JSON artifacts, not only aggregate metrics. Record model errors
and inspect a sample of successful and failed investigations. Add ambiguous,
unseen-family, and multi-fault cases before claiming broader diagnostic ability.
