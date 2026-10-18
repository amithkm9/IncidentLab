# Documentation index

The [project README](../README.md) is the public guide: setup, full demo,
architecture diagrams, Recovery Proof, measured results, and operating limits.
The files below hold technical detail or evidence that benefits from its own record.

## Architecture

- [Implementation and component map](architecture/overview.md)
- [Independent checkout contract](architecture/semantic-recovery.md)
- [Recovery Proof protocol and authority](architecture/recovery-proof.md)
- [Original scope decision](architecture/scope-decision.md), retained as design history

## Evaluation

- [Semantic acceptance and recovery](evaluation/semantic-evaluation.md): current
  contract-aware offline measurements and both unsuccessful live-model comparisons.
- [Baseline methodology](evaluation/baseline-methodology.md) and
  [recorded results](evaluation/baseline-results.md): frozen single-fault cases.
- [Exhaustive rehearsal](evaluation/rehearsal-evaluation.md) and
  [adaptive comparison](evaluation/adaptive-evaluation.md): historical HTTP-status
  recovery protocols, budgets, and limitations.
- [Recorded JSON artifacts](evaluation/results/): all published successful and
  failed runs, including the [guided Recovery Proof](evaluation/results/recovery-proof-route-price.json).

Historical results retain their original recovery definitions. The October 17
comparisons predate business-contract checks and must not be relabeled as current
semantic or live-model performance. New full runs write to ignored `artifacts/`.

## Development and project presentation

- [Development guide](development/README.md): setup, troubleshooting, packaging,
  and tooling details. [Contribution practices](../CONTRIBUTING.md).
- [Implementation work plan](development/implementation-plan.md) and [current status](../STATUS.md).
- [CV claims with evidence](career/cv.md) and [Mistral FDE case study](career/mistral-fde.md).

Shared illustrations and recorded screenshots live in `assets/`. The
[contract-aware dashboard](assets/semantic-console.png) predates the TypeScript
migration. The [earlier rehearsal capture](assets/rehearsal.png) records the
historical HTTP-only UI; neither is a current frontend validation result.
