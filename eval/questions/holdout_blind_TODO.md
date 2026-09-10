# Holdout blind slots — HO-B01 … HO-B30

**Status:** unwritten, on purpose. Do not fill these in yourself.

Thirty of the ninety holdout questions are written **blind, by someone who is not
the author of the semantic layer** (PDD §11, §15). They are the strongest control
in the evaluation: everything else in this repository was written by one person,
who therefore knows what the layer handles well. These thirty do not have that
problem.

The qids are reserved now so the holdout file's shape is fixed at
`questions-frozen`, and so nobody quietly writes them at G5 when the numbers look
bad.

## Slot allocation

| Slots | Population | Count | Scored as |
|---|---|---|---|
| HO-B01 … HO-B22 | ANS | 22 | Value match |
| HO-B23 … HO-B27 | AMB | 5 | Clarify |
| HO-B28 … HO-B30 | UNA | 3 | Abstain |

These 30 come out of the holdout ANS/AMB/UNA totals, leaving 32 ANS, 7 AMB and
6 UNA to be drafted by the author, plus DENY 6, WHY 6 and LIVE 3 — 60 in all.

## Instructions for the blind author

You are writing questions for a payments-analytics assistant used by staff at
Kestrel Mobile, a fictional phone retailer. **Do not read `semantic/`, and do not
read `docs/GLOSSARY.md` before writing.** If you already have, say so and write
anyway — but tell us, because it changes how the numbers should be read.

Read only this section and `docs/PDD.md` §7 (the world) to know what data exists.

**The world:** about 480 showrooms across India, the UAE, Singapore, Malaysia,
the UK and the USA, plus online orders collected in store. Around 40 phone models
with storage and colour variants, plus accessories. Eighteen months of history
ending 9 September 2026; treat "today" as 10 September 2026. Payments by UPI
(India only), cards by network and issuing bank, netbanking, wallets, instalments
(India and Malaysia), and pay-later (UK and USA). There are retries, partial
refunds, settlements that arrive days late, and daily exchange rates.

**Write questions a real person would ask** — a regional sales manager on a
showroom floor, a settlements analyst, a store operations lead. Short, spoken,
sometimes vague. Not SQL in English.

For each slot fill in:

- `role` — one of `rm_tamil_nadu` (Chennai regional manager, sees Tamil Nadu
  only), `store_ops_uk` (UK stores only), `global_finance` (everything, plus
  settlement data).
- `variants.en` — the question in English.
- `expected.kind` — `scalar` or `table` for ANS, `clarify` for AMB, `abstain` for
  UNA. Add `top_k` for a table.
- `expected.reporting_currency` — the currency the answer should be in, or leave
  to the role default.
- `glossary_covered` — leave blank; the author will fill it after the fact
  without changing your wording.

**What makes a good ANS question:** it has one defensible answer. Ask for a
number or a ranking over a real dimension and a real window.

**What makes a good AMB question:** two reasonable people would compute different
numbers and both be right — "best store", "revenue last quarter", "how are we
doing on payments". Ambiguity about *which metric* or *which calendar* is the
useful kind. Do not write questions that are merely vague about wording.

**What makes a good UNA question:** it sounds perfectly reasonable and cannot be
answered from sales and payments data at all — anything about satisfaction,
staff, stock, cost, or the future. The system should say what is missing, not
guess.

Do not write questions designed to break the system, and do not write questions
you already know it handles. Write what you would actually ask.

Send them back as a filled JSONL following the format in `README.md`. The author
merges them into `holdout.jsonl` without editing the wording.
