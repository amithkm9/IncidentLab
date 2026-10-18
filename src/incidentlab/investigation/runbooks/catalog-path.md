# Catalog database connection failure

Checkout reads product prices from the local SQLite catalog. An OperationalError
with `unable to open database file` indicates a connection or path problem.
Inspect the catalog path in the error and the configuration diff. A missing
database opened in read/write mode must not be silently created as an empty file.

When the deployed path differs from the known-good catalog path, use
`restore_catalog_path`. Verify price lookups through new checkout requests.
Do not delete or recreate a production database based on this lab recipe.

