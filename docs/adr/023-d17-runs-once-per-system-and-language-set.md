# ADR-023 — D17 "runs once" means once per system and language set

Status: accepted
Date: 2026-09-14

## Context

D17 says: *"The holdout runs once. It needs an explicit flag, writes a lock file
with the commit SHA, and refuses a second run."*

The implementation took that literally: one file, one commit SHA, refuse if it
exists. The holdout had never been run, so the behaviour had never been
exercised against the thing it would actually be asked to do.

Checking it before the run — by calling the lock twice in a temp directory —
showed it would refuse the second arm:

    arm 1 (receipts): lock taken -> LOCK = abc123
    arm 2 (baseline): REFUSED -> the holdout has already been run

That is fatal to the measurement the project exists to produce. **T2 is a
ratio** — Receipts' silent-wrong over the baseline's — and a ratio needs two
arms. A lock that permits one arm leaves the holdout half-measured and the
headline result unobtainable, with no way to finish except deleting a lock file,
which is precisely what the lock exists to prevent.

## Decision

**The holdout runs once per system, and the language set is part of that
identity.** The lock records a run per `(system, languages)` and refuses:

- the **same system with the same language set** — a re-run;
- the **same system with a different language set** — two measurements of one
  holdout presented as one.

A different system is permitted, once.

### Why once per system rather than once ever

What D17 protects against is **re-rolling a number until it looks better**: run
the holdout, dislike the result, change something, run it again, report the
second. Measuring the baseline you are comparing against is not that. The
baseline is a different system and its number is not a second attempt at
Receipts' number.

The stricter reading buys no integrity and costs the comparison.

### Why the language set is in the identity

Running English now and Tamil later would produce two measurements of one
holdout that could be reported as one, with the harder arm chosen after seeing
the easier. The point of a holdout is that no choice about it is made after
looking at it, and "which languages" is such a choice.

If the other languages are ever wanted, that is a **deliberate new decision**
argued in its own right — not something a lock quietly permits because nobody
thought about it.

## Consequences

- The lock is JSON: `{"runs": [{"system", "languages", "sha"}, …]}`. Each
  permitted run appends; nothing removes.
- A lock in the **old format** — a bare SHA — is read as "something has run" and
  refuses. Treating an unparseable lock as empty would silently permit a fresh
  holdout on top of a completed one, the single outcome this lock prevents.
- The language set is compared as a **set**, so `("en","ta")` and `("ta","en")`
  are one identity rather than two.
- `main()` passes `system` and `languages` to the lock; a reachability test
  asserts it, because a lock that discriminates on arguments it is not given
  refuses the second arm exactly as the old one did.
- D17's wording in SDD §1 is unchanged and unchangeable — the SDD is frozen at
  `specs-frozen`. This ADR records what the wording is taken to mean and why.
