# ADR-005: Record and replay every model call

**Status** Accepted
**Date** 2026-09-10

## Decision

Record/replay for every model call

## Why

Reproducible evals, offline CI, zero network in tests

## Context

Evaluation numbers have to be reproducible and CI has to make zero network calls.
Keying each recording by a hash of the full request — provider, model, prompt id,
prompt SHA, messages, schema, max tokens, temperature — makes replay exact, and a
missing key raises rather than quietly falling through to the network.
