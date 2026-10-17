# Project decision

Build IncidentLab: an evidence-grounded incident investigation assistant for a
small engineering team. The product takes an alert, inspects live telemetry and
deployment changes, proposes a specific remediation, and verifies that action
inside a disposable lab.

## Why this project for an Applied AI Engineering application

- A concrete customer workflow with an outcome we can test: restoring a service.
- Python integrations, retrieval, tool calling, deployment, and evaluation in one
  coherent product.
- Failures can be generated locally, providing known ground truth without private
  customer data or manufactured performance claims.
- A useful live demo: introduce a fault, inspect evidence, review the proposed
  action, apply it to the lab, and observe recovery.

We considered a document compliance assistant (strong enterprise use case, harder
to verify correctness without domain reviewers) and a manufacturing maintenance
assistant (relevant industry, but operational data and expert labels are difficult
to obtain). IncidentLab offers the strongest immediately testable implementation
in this workspace. It is not an assertion that one project is best for every
candidate or that it guarantees an interview.

## Version 1 boundaries

Use a small checkout application, an HTTP inventory dependency, and SQLite. These
are real local HTTP and database operations; the fault switches are controlled lab
mechanisms. No Kubernetes, arbitrary shell execution, or production credentials.
Use one investigator with bounded, read-only tools. Remediation is a separate,
explicitly requested action drawn from an allowlist and restricted to the lab.

Provide a deterministic baseline that runs without an API key. Label it visibly;
never present its scores as Mistral model performance. Add the live Mistral
adapter and evaluation modes, but report them as unverified until exercised with
credentials. Retrieval starts with a transparent lexical scorer.

## Next evidence to gather

1. Compare prompt-only, retrieval, and tool-assisted Mistral runs on frozen cases.
2. Test with 2–3 engineers and record changes caused by their feedback.
3. Add multi-fault and unseen-family cases before making generalization claims.
4. Profile failure traces before choosing fine-tuning or self-hosted inference.

Official integration reference:
https://docs.mistral.ai/studio/conversations/function-calling
