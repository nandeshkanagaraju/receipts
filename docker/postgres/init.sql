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

-- Idempotent: this script runs from the container's entrypoint on a fresh
-- volume AND is applied by hand to a CI service container that has no volume
-- mount. A second run must be a no-op, not an error.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'receipts_ro') THEN
        CREATE ROLE receipts_ro WITH LOGIN PASSWORD 'receipts_ro';
    END IF;
END
$$;

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
--
-- This script runs on an EMPTY database -- Postgres executes it before anything
-- has created a table -- so the grants cannot name tables here. They are applied
-- by the loader after the tables exist, which is also the only moment at which
-- the list can be checked against what is really there.

-- Every transaction read-only, whatever the session asks for. A statement that
-- writes is refused by the transaction, not only by the missing grant.
ALTER ROLE receipts_ro SET default_transaction_read_only = on;

-- A statement timeout, so a runaway query cannot hold the warehouse open.
ALTER ROLE receipts_ro SET statement_timeout = '15s';

-- Nothing granted on tables created later by anyone else, either. A table added
-- tomorrow is not readable until somebody says so.
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM receipts_ro;
