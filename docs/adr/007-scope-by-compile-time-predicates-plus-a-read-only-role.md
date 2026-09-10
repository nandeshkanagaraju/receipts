# ADR-007: Scope by compile-time predicates plus a read-only role

**Status** Accepted
**Date** 2026-09-10

## Decision

Scope enforced by compile-time predicates and free-form table rewriting, plus a DB read-only role

## Why

Defence in depth without per-user database accounts

## Context

Per-user database accounts do not scale to demo roles and do not travel across two
engines. Instead the compiler injects a region predicate after planning, from the
auth context only, and free-form SQL has every scoped table rewritten to a scoped
derived table. A read-only database role sits underneath both. Three independent
layers, each tested with the other two disabled.
