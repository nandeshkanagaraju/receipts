# ADR-004: Lexical retrieval over the catalogue, no embeddings in core

**Status** Accepted
**Date** 2026-09-10

## Decision

Lexical retrieval (BM25 over trilingual labels and synonyms), no embeddings in core

## Why

Deterministic, offline, testable. Embeddings are an ablation, not a dependency

## Context

BM25 over metric names, trilingual labels and synonyms is deterministic, runs
offline, and can be asserted in a test. Embeddings would add a model dependency
and a source of run-to-run drift to a component whose whole job is to be boring.
Embedding-based retrieval stays available as an ablation, measured against this
baseline rather than assumed better than it.
