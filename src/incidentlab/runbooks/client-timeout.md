# Client timeout budget

Checkout logs an upstream timeout when its client deadline expires before the
stock lookup completes. Inspect recent timeout configuration changes, inventory
health, and inventory request durations. An error does not prove the server is
down: a healthy dependency may be slower than the configured deadline.

The known-good lab client timeout is 400 ms. `restore_timeout_budget` restores
that setting. Verify fresh checkout requests; investigate performance separately
if the service remains slow. A larger timeout is not a universal performance fix.

