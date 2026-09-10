# ADR-006: Store business_date per row

**Status** Accepted
**Date** 2026-09-10

## Decision

Business dates stored per row (`business_date`), not derived from UTC in SQL

## Why

Local-day questions become simple equality; the UTC trap stays available to the baseline

## Context

"Yesterday" means the showroom's local day, not a UTC slice. Deriving that in SQL
from a UTC timestamp and a timezone is where the five-and-a-half-hour errors come
from. Writing the showroom-local `business_date` on every fact row at generation
time turns local-day questions into simple equality, and leaves the UTC trap
available for the baseline to fall into on its own.
