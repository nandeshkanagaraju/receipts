# ADR-003: DuckDB for analytics, PostgreSQL for the operational slice

**Status** Accepted
**Date** 2026-09-10

## Decision

DuckDB over Parquet for analytics, PostgreSQL for the operational slice

## Why

Two genuinely different engines prove multi-DB; DuckDB handles 10M+ rows on one machine

## Context

Two genuinely different engines are needed to show the compiler is dialect-aware
rather than string-templated for one database. DuckDB over Parquet handles the
10M+ row warehouse on a single machine with no server to run; PostgreSQL carries
the recent operational slice and the `customers` table that never enters the
semantic layer. Their 90-day overlap is what the cross-adapter equality test runs
on.
