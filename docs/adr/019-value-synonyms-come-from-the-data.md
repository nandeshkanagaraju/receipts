# ADR-019: Value synonyms come from the data and the glossary, never from the questions

**Status** Accepted
**Date** 2026-09-13

## Context

The M14 dev run left 62 of 108 answerable questions unanswered. 18 of those were
`UNKNOWN_FILTER_VALUE`: the planner passes a place name through in the script the
question was asked in — `चेन्नई`, `சென்னை`, `தமிழ்நாடு` — and the value index,
built from the warehouse, holds `Chennai` and `Tamil Nadu`. Six distinct values
accounted for all 18, and they were overwhelmingly Hindi and Tamil. Receipts
answered 12 of 36 English answerable questions and 4 of 36 in each Indic
language; this is most of that 22-point gap.

SDD §9.1 rule 3 already required "case-insensitive and trilingual-synonym
matching". It had never been built beyond six English aliases for `country`.

The hazard is obvious and worth naming: the cheapest way to close 18 abstentions
is to add six synonyms. That would move the headline number and measure nothing,
because the next set of questions would name a seventh city.

## Decision

**Two sources, kept apart, and a coverage rule that makes the cheap version fail
a test.**

1. **Mechanical** (`semantic/value_synonyms.py`) is computed from the value index
   itself: `pay_later` implies "pay later" and "paylater". Every alias is a
   transformation of a string the data already holds, so a new payment method
   arrives with its aliases and nobody edits a list.

2. **Curated** (`semantic/value_synonyms.yaml`) is the trilingual layer. It is
   written by hand because nothing in the warehouse knows that Chennai is
   சென்னை — there is no localised name column, and the glossary defines metrics
   rather than naming places.

**The coverage rule is the decision.** Every dimension the curated file covers
must cover *every* value of that dimension — all 37 cities, all 18 regions, all
18 issuing banks — not the ones that failed. `test_curated_synonyms_cover_every_value_not_the_failing_ones`
enforces it, and a dimension that is deliberately not covered must be named in
`UNCOVERED` with a reason, so adding a dimension fails loudly rather than being
quietly excused.

Three further tests hold the line: every canonical value must exist in the data;
a typo (`Maduari`) must still be refused, because the difference between a
synonym and a guess is where it came from; and the file must cover several times
more values than the dev set mentions at all.

## Consequences

- 114 canonical values, 303 aliases, covering 11 of 14 string dimensions.
  `showroom` (263 values) and `model` (46) are excluded as compound proper nouns
  written alike in every language; `emi_tenure_months` is numeric.
- The fold used to build the index and the fold used to match against it are now
  **one function**, `fold_value`. They were two similar ones, and a second subtly
  different fold makes index entries unreachable in a way that looks like a
  missing synonym. NFC is the part that matters, and this is the third place in
  the codebase to need it after M8's detector and M14's glossary matcher.
- A wrong translation in this file produces a confident answer about the wrong
  city. That is a real risk and it is not mitigated by anything here beyond
  review; it is the price of a layer the warehouse cannot supply.
