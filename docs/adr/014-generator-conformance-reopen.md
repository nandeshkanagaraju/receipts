# ADR-014: the generator is reopened once, for a conformance defect, and re-tagged

**Status** Accepted
**Date** 2026-09-11

## Decision

`kestrel_gen/` is reopened **once**, for one defect: the generated world held no
`authorized` payment attempts, though SDD §5.2 declares the status and PDD §6.2
lists authorised-versus-captured as one of the ten traps.

The fix gives roughly 2% of card attempts the `authorized` status. A new tag,
**`gen-frozen-2`**, records the re-freeze. **`gen-frozen` is not moved.** Both
tags stay in the history and `LIMITATIONS.md` names both.

From `gen-frozen-2`, the original rule resumes: `kestrel_gen/` is never edited
again, and a defect found later goes to `LIMITATIONS.md`.

## Why this is allowed, and why it is not a precedent

The rule that a frozen generator is never edited exists to stop the *world* being
tuned to the *results* — regenerating until the numbers look better, or widening
a definition once a system scores badly against it.

None of that is in play:

- **No system has run.** There is no agent, no semantic layer, no compiler, no
  eval run. M3 built reference answers; nothing has been scored against them.
  There is no result this change could have been chosen to improve.
- **The defect is conformance, not taste.** SDD §5.2 is frozen at `specs-frozen`
  and declares `status ∈ (authorized, captured, failed)`. The artifact had 0
  authorised rows. The artifact was wrong about the spec, and the spec is the
  frozen one.
- **The alternative was to lose a trap.** `status = 'captured'` and
  `status <> 'failed'` returned the identical figure — verified,
  3,416,905,003,997 minor units on non-test attempts. Six ANS questions carry the
  `authorised_vs_captured` tag and none of them could tell a system that models
  §4.2 from one that ignores it. Recording that in `LIMITATIONS.md` and moving on
  would have meant publishing a trap result that measured nothing.

The narrowness is the point. One defect, named in advance, fixed before any
measurement exists, with the old tag left in place so the history shows exactly
what changed and when.

## What changed

`kestrel_gen/distributions.py` gains `AUTHORIZED_CARD_SHARE`, `AUTHORIZED_STREAM`
and `_authorise_expired_holds()`, called once after the fact tables are
concatenated. Nothing else in the generator is touched.

An authorised attempt is one that **reserved the customer's funds and never took
them** — the hold expired, or was voided. It carries no `failure_reason`, because
it is not a decline. It is never revenue (§4.2). The order may still be paid by a
later attempt on the same or another method, or end abandoned.

**Card only.** UPI, netbanking and wallet settle or decline in one step; a
two-phase authorise-then-capture is a card-rail behaviour.

### The conversion is applied to attempts that already failed

This is the design decision that makes the change safe to bolt onto a frozen
generator, and it is worth stating plainly rather than burying in the diff.

A naive implementation would draw the authorisation before the capture outcome.
That consumes numbers from the main generator stream, which shifts every
subsequent draw and rebuilds a *different* world — different orders, different
amounts, different placements for all eight planted anomalies and all four sealed
ones. Every gate would be back in play, and a re-seeded world is exactly what
this project refuses to do after a measurement exists.

Instead the pass runs over the assembled table, converts a share of the card
attempts that **already failed**, and draws from its own stream
(`seed ^ AUTHORIZED_STREAM`). Consequences:

- **No capture becomes an authorisation**, so `captured_any`, paid status,
  refunds, settlements and every planted anomaly are untouched.
- Every anomaly and sealed plant selects on `status == "captured"` — positively,
  never as `!= "failed"` — so none of them can see the new value.
- The rest of the world is **byte identical** to the run before the function
  existed. Only the status and `failure_reason` of the converted rows differ.

The Bernoulli draw is per eligible attempt rather than an exact count: a realised
share of exactly 2.000% is an artefact no real acquirer produces.

### What this deliberately changes

- `status <> 'failed'` now **overstates** captured money. That is the whole
  point: it is the mistake §4.2 describes, and it is now detectable.
- `failure_rate_by_reason` (§2.10) loses the mass that was wrongly attached to
  an outcome that was not a decline. A hold that expires has no decline reason,
  and giving it one was the pre-existing error.
- `data_version` changes, so every reference answer is recomputed.

## Consequences

- New tag `gen-frozen-2`. `gen-frozen` stays where it is.
- **Freeze tooling and `docs/FREEZE_MANIFEST.json` follow the *latest* gen tag.**
  `scripts/freeze_gen.py` resolves the newest `gen-frozen*` tag rather than a
  literal, and the recorded `generator_sha256` is the hash at that tag. The
  tag-conditioned tests hold against the latest, not the first.
- Invariants extended, and they are the acceptance criteria for this change:
  - an `authorized` attempt never counts as a capture, anywhere;
  - a paid order still has at least one captured attempt;
  - more than one capture on an order still happens only on the A6 pairs.
- The full M2 gate set is re-run: the 14/14 dev/eval confirm gate, the sealed
  gate (reported as *k* of 5, and the re-freeze is abandoned if *k* < 5),
  determinism across a fresh process, and the realism table — which now carries
  the authorised share per country.
- The six `authorised_vs_captured` questions are re-checked individually:
  `status = 'captured'` and `status <> 'failed'` must now **differ** for each. If
  any still agrees, the trap is still not measured there and it is recorded.
- `LIMITATIONS.md` keeps the original section describing the defect, rewritten to
  say it was fixed, when, and under which tag — rather than deleted, because the
  record that the artifact was once wrong about its own spec is worth keeping.
