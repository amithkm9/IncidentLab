# IncidentLab documentation

Start with the [project overview](../README.md), then follow the path that fits
what you want to understand or reproduce.

| Goal | Read |
| --- | --- |
| Try the silent-failure recovery workflow | [Demo walkthrough](guides/DEMO.md) |
| Build, run, and check a change | [Development guide](development/README.md) |
| Understand components and authority boundaries | [Architecture](architecture/ARCHITECTURE.md) |
| Understand independent business-contract verification | [Semantic recovery](architecture/SEMANTIC_RECOVERY.md) |
| See what each proposed fix contributes | [Recovery Proof](architecture/RECOVERY_PROOF.md) |
| Inspect current offline and failed live-model results | [Semantic evaluation](evaluation/SEMANTIC_EVALUATION.md) |
| Reproduce the single-fault comparison | [Baseline methodology](evaluation/EVALUATION.md) and [recorded baseline](evaluation/BASELINE_RESULTS.md) |
| Inspect historical HTTP-status recovery comparisons | [Exhaustive rehearsal](evaluation/REHEARSAL_EVALUATION.md) and [adaptive comparison](evaluation/ADAPTIVE_EVALUATION.md) |
| Explain the project to an engineering interviewer | [CV claims](career/CV.md) and [Mistral FDE case study](career/MISTRAL_FDE.md) |
| Review scope decisions and remaining work | [Original decision](architecture/DECISION.md), [current work plan](development/WORK_PLAN.md), and [status](../STATUS.md) |

```text
docs/
├── architecture/       Components, contracts, and design decisions
├── guides/             User-facing demo workflow
├── evaluation/         Protocols, denominators, and interpretation
│   └── results/        Recorded JSON summaries; successful and failed runs
├── career/             Evidence-grounded project and CV presentation
├── development/        Setup, quality checks, and active work plan
└── assets/             Shared SVG diagrams and actual application captures
```

Historical results remain next to their protocols rather than being deleted or
silently updated. The October 17 comparisons used HTTP-status recovery and
predate business-contract checks. Current semantic protocols distinguish
transport success, contract acceptance, offline policy recovery, and live-model
results. Tracked JSON summaries preserve their original contents; new full runs
write to the ignored repository-root `artifacts/` directory.

The contract-aware screenshot is
[semantic-console.png](assets/semantic-console.png). The historical
[rehearsal capture](assets/rehearsal.png) documents the earlier HTTP-only UI;
it does not validate the current frontend build.
