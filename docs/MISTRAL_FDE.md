# Building IncidentLab for a Mistral FDE conversation

The customer problem is a broken checkout with several plausible fixes and a
limited incident window. A useful agent must decide what evidence to gather,
what experiment is worth running, when to stop, and what an operator can trust.
An impressive demo should make those decisions inspectable and measure their
cost. Adding more model calls alone does not establish value.

This direction fits the context engineering, orchestration, evaluation, customer
integration, and delivery responsibilities described in Mistral's
[FDE role](https://jobs.ashbyhq.com/mistral.ai/647be1ec-19d1-421c-9c49-6bbf12c0c93a).
That is a design rationale, not a claim that a project guarantees hiring success.

## The feature: an agent that learns from a failed recovery experiment

![Adaptive recovery loop: observations, Mistral plan selection, isolated experiment, new evidence, and operator approval](assets/adaptive-loop.svg)

The existing investigator proposes one action. The new recovery planner selects
a plan from fresh observations, tests it in a copy, observes the newly exposed
failure, and chooses the next plan. In the route-plus-pricing scenario:

1. Checkout fails with a dependency route error.
2. A route repair in an isolated copy reveals a pricing exception.
3. A second experiment starts from the original snapshot and tests the route
   repair together with a release rollback.
4. The operator reviews the passing plan and explicitly promotes it. Fresh
   requests establish whether the active lab recovered.

This is a design target for the live model, not a recorded Mistral success claim.
The offline adaptive policy provides a working, clearly labeled reference.
Neither policy is given scenario names, expected actions, or hidden fault flags.

## Where Mistral fits

| Product/capability | Useful role in this project | Status |
| --- | --- | --- |
| Mistral Conversations + local function tools | Choose the next recovery experiment from observed evidence; retain the results in the next context | Implemented adapter; live quality unmeasured |
| Mistral chat completion + read-only function calling | Diagnose the first visible fault and cite collected observations | Existing adapter; live quality unmeasured |
| Mistral Document AI / OCR | Import a customer's scanned runbooks with page provenance, then evaluate whether that context improves decisions | Proposed next customer-data integration |
| Vibe + an MCP integration | Let an engineer inspect the lab from their existing assistant while keeping mutation approval in IncidentLab | Proposed workflow integration |
| Forge / model customization | Improve a demonstrated recurring failure using reviewed training data and held-out evaluation | Deferred until error analysis justifies it |

Conversations supports local custom tools and can be used directly with a model;
a separately provisioned Agent is optional. IncidentLab uses `store: false` and
keeps its experiment record locally. Requests still send the selected lab
observations to Mistral's API; this flag is not an assertion about every aspect of
provider retention. [Agents and Conversations](https://docs.mistral.ai/studio/agents/agents-api),
[tool execution model](https://docs.mistral.ai/studio/agents/agent-tools).

Document AI extracts structured document content, making it a plausible entry
point for existing operational manuals. Vibe supports work and coding workflows;
Forge targets model customization. Their inclusion above is an opportunity map,
not a claim that IncidentLab already integrates every product.
[Document AI](https://docs.mistral.ai/studio/document-processing/basic_ocr),
[Mistral products](https://mistral.ai/products/).

## Use it now

Start the app and inject a compound incident. In **Fix rehearsal**, select
**Adaptive · offline policy**, leave the experiment budget at four, and run it.
Inspect the failed first experiment and the updated plan in the decision trail.
The active lab stays unchanged until **Apply plan & verify**.

For the Mistral agent, configure `MISTRAL_API_KEY` in the server environment or
local Compose `.env`, restart the app, and choose **Adaptive · Mistral agent**.
`MISTRAL_MODEL` selects the model. Pin a provider model version for a repeatable
evaluation. Credentials remain server-side. Do not paste keys into an issue,
chat, browser field, or repository file that will be committed.

The interface reports the saved run's policy, budget, model, API calls, tokens,
and cost when operator-supplied prices exist. Invalid plans and provider errors
do not silently become successful offline runs. The agent can propose only
allowlisted lab actions; it cannot call arbitrary shell commands or promote a
plan itself. A passing two-action plan is the smallest successful **tested**
plan, not proof that every smaller alternative was evaluated.

## The comparison that matters

Run both offline strategies with the same candidate budget and fresh independent
labs. Keep the failures in the denominator:

```sh
docker compose --profile eval run --build --rm eval \
  incidentlab-adaptive-eval --strategies adaptive,ordered \
  --seeds 11,23,37 --max-experiments 4 \
  --output artifacts/adaptive-comparison.json
```

The ordered comparator tries the fixed action order and stops when a passing
plan is found or its budget runs out. The adaptive policy selects from observed
errors. This comparison tests adaptive selection against a simple fixed order;
it does not establish superiority over a competent engineer or another LLM.
The existing exhaustive search remains available as a broader-budget reference.

The recorded offline run recovered **24/24 fault episodes with 33 candidate
experiments**, including all nine compound cases. Fixed-order search recovered
12/24 with 78 candidates; both preserved 6/6 no-action controls. The four-candidate
ceiling prevents that particular fixed order from reaching its fifth single
action or any pair, which explains an important part of the gap.
[Recorded protocol, results, and limitations →](ADAPTIVE_EVALUATION.md)

After credentials and model access are ready, explicitly enable paid model calls:

```sh
docker compose --profile eval run --build --rm eval \
  incidentlab-adaptive-eval --strategies adaptive,ordered,mistral \
  --seeds 42 --max-experiments 4 --allow-paid-api \
  --output artifacts/mistral-adaptive-smoke.json
```

Report recovery, compound recovery, healthy/missing-evidence abstention, execution
errors, experiments, HTTP requests, latency, API tokens, and cost together. There
is no live Mistral score until a real artifact exists. Mocked API tests verify
the integration contract and failure boundaries, not model reasoning quality.

## A credible customer pilot

**Discovery:** interview two or three on-call engineers. Identify one frequent
incident family, what evidence they can access, the decisions they make, the
actions they are allowed to approve, and the cost of a wrong recommendation.
Save the resulting changes to the product, not just interview notes.

**Integration:** begin with a read-only telemetry adapter and a reviewed runbook
collection. Preserve source IDs and timestamps. Customer data requires access
control, data handling agreement, retention policy, and tenant isolation before
this local demo could serve multiple organizations.

**Acceptance:** agree on a frozen incident set, an experiment and token budget,
recovery criteria, abstention rules, and an acceptable failure rate. Compare
against the customer's current workflow. Measure time to a verified proposal;
do not rename lab execution time as production MTTR.

**Rollout:** first replay incidents, then run in observation-only mode beside the
on-call engineer. Production cloning is a separate engineering problem: database
side effects, external dependencies, secrets, and resource limits must be handled
explicitly. Retain an operator approval boundary and a rollback procedure.

**Handoff:** deliver a deployable package, configuration guide, evaluation
artifact, monitoring plan, failure playbook, and a short demonstration. Explain
one rejected approach and the evidence behind the choice.

## Highest-value next increments

1. **Semantic recovery checks.** An HTTP 200 can contain a wrong price. Add
   business invariants and a silent-corruption scenario before stronger recovery
   claims. This is more valuable than another dashboard metric.
2. **Document AI onboarding.** Import real, approved runbooks; show page-linked
   evidence and measure retrieval/decision quality against lexical search.
3. **Live model error analysis.** Compare a pinned small and larger Mistral model
   on the same budgets, then optimize the error category that actually dominates.
4. **One real telemetry integration.** Translate a supported customer export
   into the existing observation contract. Establish whether the workflow helps
   engineers before adding more infrastructure.

Current boundaries: a local HTTP/SQLite simulator, a finite action allowlist,
known fault families, sampled HTTP-status verification, and no customer trial.
No production recovery, reduced MTTR, or first-ever novelty claim is made.

[Project overview](../README.md) · [Architecture](ARCHITECTURE.md) · [CV wording](CV.md)
