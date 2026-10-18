# Building IncidentLab for a Mistral FDE conversation

The customer problem is a checkout that may look healthy while charging the
wrong amount. A recovery assistant needs an agreed business acceptance rule,
evidence for its next experiment, and a clear boundary for operator approval.
IncidentLab makes those decisions inspectable and records both the benefit and
cost of experiments, including unsuccessful live-model attempts.

This direction fits the context engineering, orchestration, evaluation, customer
integration, and delivery responsibilities described in Mistral's
[FDE role](https://jobs.ashbyhq.com/mistral.ai/647be1ec-19d1-421c-9c49-6bbf12c0c93a).
That is a design rationale, not a claim that a project guarantees hiring success.

## The feature: recovery checked against the customer's requirement

![A route repair returns HTTP 200 with an incorrect total; measured business-contract failure informs the next recovery experiment](assets/semantic-recovery.svg)

The existing investigator proposes one action. The new recovery planner selects
a plan from fresh observations, tests it in a copy, observes the newly exposed
failure, and chooses the next plan. In `route_and_price_drift`:

1. Checkout fails with a dependency route error.
2. A route repair in an isolated copy returns HTTP 200 but charges $13.00 for a
   notebook whose independent contract requires $12.00.
3. A second experiment starts from the original snapshot and tests the route
   repair together with a release rollback.
4. The operator reviews the passing plan and explicitly promotes it. Fresh
   requests must pass both HTTP and contract verification in the active lab.

The offline adaptive policy provides a working, clearly labeled reference for
this sequence. The first live-model smoke run did not reliably reproduce it;
its failures are recorded below. Neither policy receives scenario names,
expected repair actions, or hidden fault flags. Declared business requirements
are legitimate verification inputs, independent of the faulty pricing code.

The `checkout-response` contract is versioned and hashed. It checks product
identity, exact monetary totals, response fields, and strict JSON structure.
Its metadata travels with evidence and contributes to the promotion fingerprint.
[Contract design and implemented boundaries →](SEMANTIC_RECOVERY.md)

## Where Mistral fits

| Product/capability | Useful role in this project | Status |
| --- | --- | --- |
| Mistral Conversations + local function tools | Choose recovery experiments from measured HTTP and contract evidence; retain results in the next context | Implemented; first pinned live smoke retained for error analysis |
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

Start the app and choose **Try the silent-failure demo**. In **Fix rehearsal**, select
**Adaptive · offline policy**, leave the experiment budget at four, and run it.
Inspect the route-only HTTP 200 result, its failed price check, and the updated
plan in the decision trail.
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

First test the acceptance rule itself. Apply HTTP-only and contract-aware gates
to the same saved responses, then evaluate policy recovery in separate labs:

```sh
docker compose --profile eval run --build --rm eval \
  incidentlab-semantic-eval --split test --strategies adaptive \
  --max-experiments 4 --output artifacts/semantic-test.json
```

The recorded offline run contains 18 episodes and 72 paired plan trials.
HTTP-only checks accepted 39 trials; nine of those were false recoveries under
the independent contract. Contract checks accepted 30. The separate offline
adaptive arm recovered 12/12 fault episodes with 18 candidate experiments and
preserved 6/6 no-action controls.
[Semantic protocol, recorded results, and limits →](SEMANTIC_EVALUATION.md)

The earlier adaptive-versus-ordered comparison remains useful historical
evidence. On October 17, before semantic verification, the offline policy
recovered 24/24 fault episodes in 33 candidates; fixed-order search recovered
12/24 in 78, and both preserved 6/6 controls. Its four-candidate ceiling prevented
that fixed order from reaching its fifth single action or any pair. The result
does not establish superiority over a competent engineer or another LLM.
[Historical protocol and limitations →](ADAPTIVE_EVALUATION.md)

After credentials and model access are ready, explicitly enable paid model calls:

```sh
docker compose --profile eval run --build --rm eval \
  incidentlab-semantic-eval --split smoke --strategies adaptive,mistral \
  --max-experiments 4 --allow-paid-api \
  --output artifacts/mistral-semantic-smoke.json
```

Report recovery, compound recovery, healthy/missing-evidence abstention, execution
errors, experiments, HTTP requests, latency, API tokens, and cost together.
Mocked API tests verify integration contracts and failure boundaries; live
artifacts establish what the model actually did under the specified conditions.

## What the first live run taught us

The first pinned `mistral-small-2603` smoke run recovered **1/4 fault cases**,
preserved **2/2 no-action controls**, and recorded **two provider errors**. A
compound case exposed a decision error: a later plan forgot an earlier repair,
even though each experiment restarts from the original snapshot.

This is a useful engineering result, not a successful-quality headline. Retain
the failed artifact, distinguish provider failures from planning failures,
clarify tool effects and snapshot semantics, then measure a fresh pinned run.
The follow-up added explicit full-plan context and safe provider diagnostics.
It also recovered 1/4 faults and preserved both controls, but recorded three
HTTP 429 errors. It did not demonstrate a recovery-quality improvement.
[Retained live evidence and subsequent comparisons →](SEMANTIC_EVALUATION.md)

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

1. **Close the observed live-model gaps.** Preserve required actions across
   same-snapshot trials, diagnose provider failures, and verify improvements
   against the retained cases and a fresh run.
2. **Document AI onboarding.** Import real, approved runbooks; show page-linked
   evidence and measure retrieval/decision quality against lexical search.
3. **Broader business acceptance.** Extend the implemented price/product contract
   with customer-approved invariants and ambiguity cases; compare pinned models
   at the same declared budgets.
4. **One real telemetry integration.** Translate a supported customer export
   into the existing observation contract. Establish whether the workflow helps
   engineers before adding more infrastructure.

Current boundaries: a local HTTP/SQLite simulator, a finite action allowlist,
known fault families, sampled HTTP and declared-contract verification, and no customer trial.
No production recovery, reduced MTTR, or first-ever novelty claim is made.

[Project overview](../README.md) · [Architecture](ARCHITECTURE.md) · [CV wording](CV.md)
