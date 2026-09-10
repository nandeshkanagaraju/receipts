# ADR-008: One-screen Vite + React SPA served by FastAPI

**Status** Accepted
**Date** 2026-09-10

## Decision

One-screen Vite + React SPA, built to static files served by FastAPI, over REST + SSE

## Why

Streaming agent steps is the core UX; one screen needs no framework router; one deployable

## Context

The front end's job is to show a non-technical person getting a trustworthy answer.
That is one screen: a conversation, an answer canvas, a receipt, and two drawers.
A framework router earns nothing when there is nothing to route between, and a
separately deployed front end doubles the operational surface of a demo that must
come up in three commands. Vite builds to static files that FastAPI serves at `/`,
so the web app ships inside the API image and there is one deployable.
