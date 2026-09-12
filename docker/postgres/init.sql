-- receipts_ro: the third read-only layer for Postgres (SDD §12.3, D8).
--
-- DuckDB's equivalent is a read-only file handle; Postgres has a real role, and
-- it is the layer that holds when the AST guard and the adapter are both off.
-- That is not hypothetical: D8 requires each layer to be tested alone, and this
-- is what the third test leans on.
--
-- The role is deliberately built by REVOKE-then-GRANT rather than by granting
-- what it needs. A role created with defaults inherits PUBLIC's privileges, and
-- "we never granted INSERT" is not the same sentence as "INSERT is revoked".

CREATE ROLE receipts_ro WITH LOGIN PASSWORD 'receipts_ro';

-- Start from nothing.
REVOKE ALL ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC;

GRANT USAGE ON SCHEMA public TO receipts_ro;

-- SELECT only, and only on the allowlisted tables. `customers` is deliberately
-- absent: SDD §5.2 keeps it out of the semantic layer, and this makes that true
-- at the database as well, so a free-form query cannot reach it even with the
-- guard disabled.
GRANT SELECT ON
    orders, order_items, payment_attempts, refunds,
    settlements, settlement_items,
    showrooms, cities, regions, countries, products, product_notes, prices, fx_rates
TO receipts_ro;

-- Every transaction read-only, whatever the session asks for. A statement that
-- writes is refused by the transaction, not only by the missing grant.
ALTER ROLE receipts_ro SET default_transaction_read_only = on;

-- A statement timeout, so a runaway query cannot hold the warehouse open.
ALTER ROLE receipts_ro SET statement_timeout = '15s';

-- Nothing granted on tables created later, either.
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM receipts_ro;
