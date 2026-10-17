# Pricing application regression

A TypeError in checkout pricing after deploying checkout-1.1 indicates that the
discount calculation received an invalid value. Compare the release change with
the exception. Successful stock lookup logs distinguish this from dependency
failure. A healthy liveness endpoint does not test the checkout code path.

`rollback_checkout_release` returns the lab to checkout-1.0. Verify fresh checkout
requests and their totals. A production rollout would also require its own
compatibility review; this lab has no schema migrations.

