# Describing IncidentLab on a CV

Use specific engineering contributions and reproducible results. Describe the
project as an incident investigation and remediation experiment platform, rather
than claiming production deployment, unprecedented novelty, or model accuracy
that has not been evaluated.

## Engineering bullets

- Built an incident investigation platform using Python, FastAPI, SQLite, and
  real HTTP services, with evidence-linked diagnoses, bounded Mistral tool use,
  and an offline mode for reproducible development.
- Implemented isolated fix rehearsal: copy application state, compare a
  no-action control with up to 15 candidate remediation plans, and choose a
  minimal plan using measured checkout responses before changing the active lab.
- Integrated Mistral Conversations with validated local function tools for
  adaptive recovery experiments, including evidence citations, experiment
  budgets, explicit abstention, provider token/cost accounting, and operator-gated
  promotion. Live model quality remains to be evaluated.
- Built an offline adaptive reference that recovered 24/24 known fault episodes,
  including nine compound cases, in 33 candidate experiments while preserving
  all six no-action controls; added a reproducible comparison and CI evaluation.
- Improved verified fault recovery from 62.5% (15/24) to 100% (24/24) versus a
  one-shot rule-based baseline in a controlled HTTP/SQLite benchmark, resolving
  9/9 compound-fault episodes while preserving no-action decisions in 6/6 controls.

Choose two or three bullets relevant to the role. These measured results come
from the 2026-10-17 run, documented in
[REHEARSAL_EVALUATION.md](REHEARSAL_EVALUATION.md) and the tracked
[result summary](rehearsal-results.json). Preserve the full generated
`artifacts/rehearsal-test.json` when presenting the result.

The adaptive result has a separate [protocol](ADAPTIVE_EVALUATION.md) and
[recorded summary](adaptive-results.json). It measures an engineered known-error
policy, not Mistral reasoning quality. For an FDE application, lead with the
integration and evaluation work; discuss the limitations alongside the numbers.

## A shorter results bullet

“Improved recovery by **37.5 percentage points** across 24 controlled fault
episodes by rehearsing remediation plans in isolated application copies,
with **6/6** no-action controls preserved.”

Explain that this compares a one-shot rule-based baseline with a more expensive
bounded search: the run executed 405 candidate experiments and 1,305 rehearsal
requests. Median complete episode time was 15.72 ms for the baseline and
1,717.40 ms for rehearsal; the recovery improvement has a compute cost. The 30
episodes repeat 10 known scenarios across three seeds; they are not independent
production incidents. Do not call the result “AI accuracy” or “reduced MTTR.”

## Interview demonstration

Inject a compound fault, inspect the evidence, and show why one proposed action
leaves checkout failing. Run rehearsal, compare the unsuccessful single fixes
with the successful two-action plan, then promote that plan and show fresh
verification. Explain the resource budget and control case alongside the
recovery result. Discuss what would be required to extend this approach to
stateful production systems and why this lab does not establish that safety.
