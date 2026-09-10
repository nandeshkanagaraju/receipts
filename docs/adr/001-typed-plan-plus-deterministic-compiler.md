# ADR-001: Typed plan plus deterministic compiler

**Status** Accepted
**Date** 2026-09-10

## Decision

Model outputs a typed plan; a deterministic compiler writes SQL

## Why

The thesis. Correctness lives in code that can be tested

## Context

Text-to-SQL fails silently: a confident, well-formatted, wrong number that the
asker cannot check. Letting the model emit a typed `QueryPlan` over a governed
semantic layer, and compiling that plan to SQL in code, moves correctness out of
the model and into something testable. The model's remaining job is narrow —
understand the language, choose the plan, narrate the result — and that narrowness
is the finding we want to publish, not a limitation we are apologising for.
