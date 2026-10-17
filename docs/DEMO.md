# Three-minute demo

Start the app and open `http://127.0.0.1:8000`. Use the offline baseline unless a
Mistral key is configured. Always identify which mode is being demonstrated.

**0:00–0:30 — Introduce the failure.** Select Configuration drift and inject it.
Show the four failed checkout requests. Inventory and checkout are real local
HTTP servers; the fault changes the inventory URL path.

**0:30–1:30 — Investigate.** Run an investigation. Open Application logs and
Deployment changes. Explain the distinction between checkout's HTTP 502 and its
dependency's HTTP 404. Click the finding's supporting citation. Open the runbook
to distinguish troubleshooting guidance from live incident evidence.

**1:30–2:15 — Apply and verify.** Click Apply fix & verify. The lab restores the
known-good route. Show five fresh HTTP 200s and the new observation window.
Investigate again: the result should now be healthy with no proposed action.

**2:15–2:45 — Demonstrate abstention.** Inject Missing evidence, then investigate.
The correct finding is insufficient evidence with no executable action. The
operator can see failed requests, but the investigator lacks diagnostics.

**2:45–3:00 — Show the engineering record.** Export JSON and point to the tool
arguments, observations, provenance, latency, and limitations. Explain that the
offline suite proves this implementation's known-case behavior, not model
accuracy or production readiness.
