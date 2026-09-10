# M1 — eval set complete (150), rulings applied

---

## 1. Files created/changed

| File | What |
|---|---|
| `docs/GLOSSARY.md` | §1.7a product attribution · §5.3a method-qualified orders · §2.12 note |
| `docs/M2_NOTES.md` | §1.1a anomaly concentration · §1.1b one handset per order · §1.3 named entities · M4 tie rule · S1 excludes GB |
| `docs/adr/011-customer-id-blocked.md` | new |
| `eval/questions/eval.jsonl` | 100 → **150**, plus 9 rewrites |

## 2. Tests

**68 passed, 0.97s.** Lint, types, freeze-check green. No new tests: the entity
test (item 4) belongs to M2's TEST and is specified in `M2_NOTES` §1.3 rather
than written now, since it must run against the generated artifact.

## 3. Eval set complete

```
ANS  90/90   AMB  20/20   UNA  15/15
DENY 10/10   WHY  10/10   LIVE  5/5      total 150
glossary_covered=false 34/150 = 23%
roles: global_finance 76 · rm_tamil_nadu 40 · store_ops_uk 34
traps: attempts_vs_orders 10 · authorised_vs_captured 4 · capture_vs_settlement 10
       duplicate_captures 4 · emi 7 · fiscal_calendar 9 · local_time 4
       multi_currency 4 · partial_refunds 15 · test_transactions 3
compare 8 · series 6
```

**`make freeze-questions` now reports exactly one blocker:**

```
REFUSING to create the questions-frozen tag. 1 problem(s):
  holdout.jsonl is missing
```

## 4. Item 7 — the audit, and what it caught

I masked place, window and currency out of every question and compared skeletons
across all 210 questions. **Five colliding groups** were filter swaps and are
rewritten to change shape, not region:

| Was | Now |
|---|---|
| EV-003 orders in Coimbatore yesterday | captured GMV **by city** in Tamil Nadu yesterday |
| EV-053 orders in the US in July | **units sold** in the US in July |
| EV-061 orders in Singapore yesterday | orders **by country** yesterday — "yesterday" resolves in six timezones at once |
| EV-072 attach rate in Malaysia | attach rate **by channel** in Malaysia |
| EV-049 pending refunds from July | pending refunds **by country** |
| EV-128 attach rate by showroom in the UK | attach rate **compared month-to-date** |

One collision was a **false positive**: EV-003 vs EV-112 differ in dimension
(city vs showroom) *and* window type (day vs month); my masker was collapsing
"by city" and "by showroom" to the same token.

## 5. Item 2 — ties, and what they forced

EV-012, EV-057 and EV-058 were all rankings over duplicate captures. That metric
is near-zero almost everywhere, so most of each top-k would have been ties at
zero: the question would have been asking the system to order noise. Rewritten as
three different measures, none of them a ranking:

| qid | Now measures |
|---|---|
| EV-012 | the **value** tied up in duplicate captures (scalar) |
| EV-057 | duplicate captures as a **weekly series** — matched by time key, so zero-weeks cannot produce a spurious order |
| EV-058 | duplicates as a **share** of all captures (scalar) |

The tie rule itself is recorded in `M2_NOTES` for M4: ranks compare as groups of
equal value, order within a tie group is ignored, order between groups still
matters.

## 6. Item 1 — product attribution, and the case it creates

§1.7a: order-level money by model, storage or colour is attributed **entirely to
the order's handset**. Units are explicitly *not* affected — units count lines, so
an accessory belongs to itself.

That divergence is deliberate and now has a question: **EV-103** asks which model
brought in the most money *and* which sold the most units, in one question. The
two rankings can legitimately differ, so a system applying one rule to both gets
half of it wrong. Five batch-3 questions exercise attribution in total (EV-101,
102, 103, 104, 105).

Re-checked and updated: DV-047 and EV-048 are now well defined without an
interpretation; EV-074's interpretation says handset explicitly; EV-075's says
**each line**, since it is a units question; EV-034 is unaffected.

## 7. Item 5 — method-qualified orders

§5.3a: "EMI orders", "card-paid orders" mean orders whose **captured** attempt
used that method — not the tried rule, which applies only to success rates. The
glossary states both and shows the same order reading differently under each.

Re-checked: DV-046, DV-047, EV-060 and EV-068 are all method-qualified filters,
all now resolved by §5.3a, none needing an interpretation.

## 8. Deviations

1. **Five product-attribution questions, not four.** EV-103 needed a partner to
   be meaningful, and the money-versus-units divergence deserved its own case.
2. **`M2_NOTES` kept**, per your ruling, with the entity list added as §1.3
   rather than a separate file.
3. **The entity test is specified, not written.** It must run against the
   generated world, which does not exist until M2. `M2_NOTES` §1.3 names it as an
   M2 TEST item and lists every entity to build.

## 9. Unsure about

- **`test_transactions` sits at 3 in eval** — the minimum. Any later rewrite that
  touches EV-009, EV-023 or EV-054 drops it below the floor, and the freeze gate
  will catch it, but it is worth knowing the margin is zero.
- **EV-127 assumes FY2027 Q1 = April–June 2026**, following §1.5. That window is
  inside the loaded range; FY2026 Q1 (EV-023) is April–June 2025, also inside it.
  Both depend on the naming convention holding.
- **EV-149 is phrased as a yes-or-no** ("are any Chennai refunds still pending"),
  where an empty result is a *valid answer* rather than a failure. The M4 scorer
  needs to handle an empty LIVE result as correct when the reference is empty —
  worth a note when scoring is built.
