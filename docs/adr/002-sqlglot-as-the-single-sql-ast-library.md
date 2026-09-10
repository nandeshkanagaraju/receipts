# ADR-002: sqlglot as the single SQL AST library

**Status** Accepted
**Date** 2026-09-10

## Decision

sqlglot for SQL building, parsing, guarding, and dialect transpiling

## Why

One AST library for all four jobs means one set of semantics

## Context

The system parses SQL (the guard), builds SQL (the compiler), rewrites SQL (the
free-form scope rewrite) and transpiles it between dialects. Doing those four jobs
with four libraries would mean four subtly different ideas of what a statement
means, and the gaps between them are exactly where a guard bypass lives. One AST
library gives one set of semantics.
