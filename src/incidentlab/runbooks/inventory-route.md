# Inventory route mismatch

Checkout calls the inventory stock API at `/v1/stock`. An upstream HTTP 404
means the dependency answered but the requested route was absent. Compare the
endpoint in checkout logs with the recent configuration diff. A healthy inventory
readiness probe does not establish that the configured route is correct.

When a deployment changed the path to an unsupported route, use
`restore_inventory_route`. Verify with fresh successful checkout requests.
Do not restart a healthy dependency to correct a URL path.

