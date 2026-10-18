# Describing IncidentLab on a CV

Lead with customer correctness, integration work, and reproducible evaluation.
The project demonstrates a recovery workflow whose success criteria are
inspectable, including when the live model fails.

## Engineering bullets

- Built a Python/FastAPI incident recovery workbench with real HTTP services,
  SQLite state, 12 reproducible scenarios including four compound failures,
  isolated experiments, evidence-linked findings, and persistent audit history.
- Implemented versioned business-contract verification that detects incorrect
  prices and product IDs behind HTTP 200 responses, with exact-cent validation,
  contract fingerprints, operator-approved promotion, and fresh post-fix checks.
- Integrated Mistral Conversations with validated local function tools,
  evidence citations, experiment budgets, explicit abstention, and provider
  usage accounting; retained failed live runs for structured error analysis.
- Designed a paired acceptance benchmark that applies HTTP-only and contract-aware
  rules to the same saved responses, separately measures policy recovery, and
  retains execution failures in quality denominators.

Choose two or three bullets that fit the role. These are implemented engineering
contributions, not claims of production deployment or unmeasured model quality.

## Current measured results

The offline semantic test contained **18 controlled episodes** and **72 paired
plan trials**. HTTP-only checks accepted 39 trials; **nine of those acceptances
were false recoveries** under the independent business contract (23.08%).
Contract checks accepted 30. Separately, the offline adaptive policy recovered
**12/12 fault episodes**, preserved **6/6 no-action controls**, and used
**18 candidate experiments**. See the full
[semantic evaluation protocol and evidence](SEMANTIC_EVALUATION.md).

A concise results bullet:

> Built contract-aware recovery verification that rejected nine false HTTP-only
> recoveries among 39 accepted outcomes in 72 controlled trials; an offline
> adaptive reference restored all 12 fault episodes while preserving six
> no-action controls.

Keep the two measurements distinct: paired acceptance judges the same responses;
policy recovery applies the selected plan in a separate lab and verifies fresh
traffic. Known scenarios and repeated seeds are regression evidence, not
independent customer incidents or a model-generalization study.

## What to say about the live model

The first smoke run used pinned `mistral-small-2603`: **1/4 fault recoveries**,
**2/2 no-action controls**, and **two provider errors**. A compound case exposed a
planning mistake: a later plan omitted a repair needed by the original snapshot.
The context follow-up also recovered **1/4 faults** and preserved both controls,
with **three HTTP 429 failures**. Both reports remain part of the evaluation
record; the follow-up did not establish a quality improvement.

For an FDE conversation, explain how that failure changes the tool/context
contract, which evidence will verify a fix, and why unsuccessful attempts remain
in the denominator. Do not convert an offline score into a Mistral score or
describe a planned improvement as a measured result.

## Historical results, with their original scope

The October 17, 2026 artifacts predate semantic checks and silent-price
scenarios. Their recovery definition was five fresh HTTP 200 responses:

- Exhaustive rehearsal improved recovery from 15/24 (62.5%) to 24/24 (100%)
  against a one-shot rule-based baseline, with 9/9 compound cases recovered and
  6/6 no-action controls preserved. This used 405 candidates and 1,305 rehearsal
  requests. [Protocol](REHEARSAL_EVALUATION.md)
- The offline adaptive reference recovered 24/24 faults in 33 candidates, with
  6/6 no-action controls. The fixed-order comparator had the same candidate
  ceiling but was limited by its particular ordering.
  [Protocol](ADAPTIVE_EVALUATION.md)

These remain historical system measurements. They do not demonstrate semantic
correctness under the new contract, live AI accuracy, or reduced production MTTR.

## Interview demonstration

Use **Try the silent-failure demo**. Show the route-only plan returning HTTP 200
while charging the wrong amount, the versioned contract rejecting that result,
and the measured feedback leading to a combined plan. Promote it explicitly and
inspect five fresh contract-verified responses.

Explain the contract's source, what it does not specify, the cost of extra
experiments, and the first live-model failure. Then describe a customer pilot:
agree on acceptance rules, integrate approved telemetry, replay a frozen case
set, and measure outcomes before expanding access or automation.
