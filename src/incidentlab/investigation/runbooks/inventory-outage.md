# Inventory unavailable

Upstream HTTP 503 together with a failing inventory readiness probe indicates
dependency unavailability. Checkout can remain alive while its requests fail.
Check readiness and error logs before attributing the incident to a deployment.

In this disposable lab, `restore_inventory_service` restores the dependency's
readiness. Verify inventory readiness and fresh checkout requests. This recipe is
a lab control, not a general production restart command.

