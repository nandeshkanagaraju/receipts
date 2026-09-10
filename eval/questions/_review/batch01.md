# Batch 01 — dev.jsonl, DV-001–DV-020

**File:** `eval/questions/dev.jsonl` (lines 1–20)  
**Status:** draft, awaiting approval. Deleted at `questions-frozen`.

## Changes in this revision

**GLOSSARY §1.9 replaced — final-attempt attribution was wrong.** Your catch: an
order that tried UPI, failed, then paid by card left UPI's denominator entirely,
so UPI's success rate *rose* exactly when UPI was failing. §1.9 now specifies
**"tried" attribution** for every per-method / per-bank / per-network order-level
success rate: denominator = orders with at least one non-test attempt on that
method/bank/network; numerator = those with a captured attempt on the *same* one.
The section states explicitly that per-method rates **do not sum or reconcile to
the overall rate** — the denominators overlap, their union exceeds the order
count, so they do not partition the orders. Value and count metrics are separated
out: they follow the money to the capturing attempt, and those breakdowns *do*
sum to the total.

**Questions in this batch that depend on §1.9:**

| qid | Why it depends | Effect of the change |
|---|---|---|
| DV-001 | "UPI success rate in Chennai" — per-method order-level rate | Denominator is now orders that *tried* UPI, not orders that *ended* on UPI. Larger denominator; lower rate during a UPI incident |
| DV-010 | "Card success rate by issuing bank" — per-bank order-level rate | Same per bank; an order that tried two banks now appears in both denominators |
| DV-019 | WHY on A1, decomposing UPI success by bank | The anomaly becomes visible: under the old rule the dip partly hid itself |
| DV-040 | WHY on A5, card failures in the UK | Same, for card/network decomposition |

**Not affected, and now explicitly so:** DV-028 (attempt-level — attempts carry
their own bank, no attribution rule needed); DV-008 and DV-025 (EMI *share* is a
value metric, attributed to the capture, covered by the new "value follows the
money" clause).

**Other glossary fixes landing in this batch:**

- **§5 rewritten to map phrases, not words**, in five tables (money, counts,
  payments, time, and phrases that deliberately have no entry). "How much did we
  take" -> captured GMV; "how many orders did we take" -> orders_count; "how long
  did settlement take" -> settlement lag. A word-level map collapsed all three.
- **§2.1 orders_count** now carries a status table: `paid`, `abandoned` and
  `cancelled` all count, and "orders we got paid for" is called out as a
  different number.
- **§2.10 failure_rate_by_reason** — denominator nailed as *all attempts of any
  outcome*, with the consequence spelled out: per-reason rates sum to the overall
  attempt failure rate, not to 100%. A set summing to 100% is the
  share-of-failures, which is undefined here.
- **DV-009 reworded** to "Payment failure **rate** by reason..." so it matches the
  metric. It was a count question pointed at a rate metric.
- **§2.2** — "phone", "phone model", "handset", "device" mean handsets only;
  "units" includes accessories.
- **§2.14 unsettled_amount** — now explicitly a **snapshot at the end of the
  window** (captured on or before D, unsettled at D, no lower bound), with FX at
  each amount's own capture date so it reconciles with captured GMV.

## Batch summary

- Populations: AMB 3 · ANS 12 · DENY 1 · LIVE 1 · UNA 2 · WHY 1
- Roles: global_finance 6 · rm_tamil_nadu 9 · store_ops_uk 5
- `glossary_covered: false`: 5/20 = 25%
- Traps: attempts_vs_orders 3 · authorised_vs_captured 1 · capture_vs_settlement 1 · emi 1 · fiscal_calendar 1 · local_time 1 · multi_currency 1 · partial_refunds 1

---

## DV-001 — ANS

> **What was our UPI success rate in Chennai yesterday?**

| field | value |
|---|---|
| role | `rm_tamil_nadu (Chennai / IN-TN)` |
| as_of | `2026-09-10` |
| trap | `attempts_vs_orders` |
| glossary_covered | `true` |
| kind | `scalar` |
| reporting_currency | `None` |
| tolerance_rel | `0.001` |
| reference_sql | `DV-001.sql` |
| ta / hi / ta-Latn | empty, provenance `pending` |

<details><summary>raw JSONL line</summary>

```json
{"qid": "DV-001", "set": "dev", "population": "ANS", "role": "rm_tamil_nadu", "as_of": "2026-09-10", "trap": "attempts_vs_orders", "glossary_covered": true, "variants": {"en": "What was our UPI success rate in Chennai yesterday?", "ta": "", "hi": "", "ta-Latn": ""}, "translation_provenance": {"ta": "pending", "hi": "pending", "ta-Latn": "pending"}, "authored_by": "nandesh", "expected": {"kind": "scalar", "reference_sql": "DV-001.sql", "reporting_currency": null, "tolerance_rel": 0.001}}
```
</details>

## DV-002 — ANS

> **How many orders did we take across Tamil Nadu yesterday?**

| field | value |
|---|---|
| role | `rm_tamil_nadu (Chennai / IN-TN)` |
| as_of | `2026-09-10` |
| trap | `local_time` |
| glossary_covered | `true` |
| kind | `scalar` |
| reporting_currency | `None` |
| tolerance_rel | `0.001` |
| reference_sql | `DV-002.sql` |
| ta / hi / ta-Latn | empty, provenance `pending` |

<details><summary>raw JSONL line</summary>

```json
{"qid": "DV-002", "set": "dev", "population": "ANS", "role": "rm_tamil_nadu", "as_of": "2026-09-10", "trap": "local_time", "glossary_covered": true, "variants": {"en": "How many orders did we take across Tamil Nadu yesterday?", "ta": "", "hi": "", "ta-Latn": ""}, "translation_provenance": {"ta": "pending", "hi": "pending", "ta-Latn": "pending"}, "authored_by": "nandesh", "expected": {"kind": "scalar", "reference_sql": "DV-002.sql", "reporting_currency": null, "tolerance_rel": 0.001}}
```
</details>

## DV-003 — ANS

> **Total captured GMV across all countries last month, in US dollars.**

| field | value |
|---|---|
| role | `global_finance (all + finance)` |
| as_of | `2026-09-10` |
| trap | `multi_currency` |
| glossary_covered | `true` |
| kind | `scalar` |
| reporting_currency | `USD` |
| tolerance_rel | `0.001` |
| reference_sql | `DV-003.sql` |
| ta / hi / ta-Latn | empty, provenance `pending` |

<details><summary>raw JSONL line</summary>

```json
{"qid": "DV-003", "set": "dev", "population": "ANS", "role": "global_finance", "as_of": "2026-09-10", "trap": "multi_currency", "glossary_covered": true, "variants": {"en": "Total captured GMV across all countries last month, in US dollars.", "ta": "", "hi": "", "ta-Latn": ""}, "translation_provenance": {"ta": "pending", "hi": "pending", "ta-Latn": "pending"}, "authored_by": "nandesh", "expected": {"kind": "scalar", "reference_sql": "DV-003.sql", "reporting_currency": "USD", "tolerance_rel": 0.001}}
```
</details>

## DV-004 — ANS

> **How much money did we actually collect in the UK last week?**

| field | value |
|---|---|
| role | `store_ops_uk (GB)` |
| as_of | `2026-09-10` |
| trap | `authorised_vs_captured` |
| glossary_covered | `true` |
| kind | `scalar` |
| reporting_currency | `GBP` |
| tolerance_rel | `0.001` |
| reference_sql | `DV-004.sql` |
| ta / hi / ta-Latn | empty, provenance `pending` |

<details><summary>raw JSONL line</summary>

```json
{"qid": "DV-004", "set": "dev", "population": "ANS", "role": "store_ops_uk", "as_of": "2026-09-10", "trap": "authorised_vs_captured", "glossary_covered": true, "variants": {"en": "How much money did we actually collect in the UK last week?", "ta": "", "hi": "", "ta-Latn": ""}, "translation_provenance": {"ta": "pending", "hi": "pending", "ta-Latn": "pending"}, "authored_by": "nandesh", "expected": {"kind": "scalar", "reference_sql": "DV-004.sql", "reporting_currency": "GBP", "tolerance_rel": 0.001}}
```
</details>

## DV-005 — ANS

> **What was the average settlement lag in August?**

| field | value |
|---|---|
| role | `global_finance (all + finance)` |
| as_of | `2026-09-10` |
| trap | `capture_vs_settlement` |
| glossary_covered | `true` |
| kind | `scalar` |
| reporting_currency | `None` |
| tolerance_rel | `0.001` |
| reference_sql | `DV-005.sql` |
| ta / hi / ta-Latn | empty, provenance `pending` |

<details><summary>raw JSONL line</summary>

```json
{"qid": "DV-005", "set": "dev", "population": "ANS", "role": "global_finance", "as_of": "2026-09-10", "trap": "capture_vs_settlement", "glossary_covered": true, "variants": {"en": "What was the average settlement lag in August?", "ta": "", "hi": "", "ta-Latn": ""}, "translation_provenance": {"ta": "pending", "hi": "pending", "ta-Latn": "pending"}, "authored_by": "nandesh", "expected": {"kind": "scalar", "reference_sql": "DV-005.sql", "reporting_currency": null, "tolerance_rel": 0.001}}
```
</details>

## DV-006 — ANS

> **What is our refund rate in Tamil Nadu this month?**

| field | value |
|---|---|
| role | `rm_tamil_nadu (Chennai / IN-TN)` |
| as_of | `2026-09-10` |
| trap | `partial_refunds` |
| glossary_covered | `true` |
| kind | `scalar` |
| reporting_currency | `None` |
| tolerance_rel | `0.001` |
| reference_sql | `DV-006.sql` |
| ta / hi / ta-Latn | empty, provenance `pending` |

<details><summary>raw JSONL line</summary>

```json
{"qid": "DV-006", "set": "dev", "population": "ANS", "role": "rm_tamil_nadu", "as_of": "2026-09-10", "trap": "partial_refunds", "glossary_covered": true, "variants": {"en": "What is our refund rate in Tamil Nadu this month?", "ta": "", "hi": "", "ta-Latn": ""}, "translation_provenance": {"ta": "pending", "hi": "pending", "ta-Latn": "pending"}, "authored_by": "nandesh", "expected": {"kind": "scalar", "reference_sql": "DV-006.sql", "reporting_currency": null, "tolerance_rel": 0.001}}
```
</details>

## DV-007 — ANS

> **Top 5 UK showrooms by units sold last month.**

| field | value |
|---|---|
| role | `store_ops_uk (GB)` |
| as_of | `2026-09-10` |
| trap | `None` |
| glossary_covered | `true` |
| kind | `table` · top_k `5` |
| reporting_currency | `None` |
| tolerance_rel | `0.001` |
| reference_sql | `DV-007.sql` |
| ta / hi / ta-Latn | empty, provenance `pending` |

<details><summary>raw JSONL line</summary>

```json
{"qid": "DV-007", "set": "dev", "population": "ANS", "role": "store_ops_uk", "as_of": "2026-09-10", "trap": null, "glossary_covered": true, "variants": {"en": "Top 5 UK showrooms by units sold last month.", "ta": "", "hi": "", "ta-Latn": ""}, "translation_provenance": {"ta": "pending", "hi": "pending", "ta-Latn": "pending"}, "authored_by": "nandesh", "expected": {"kind": "table", "reference_sql": "DV-007.sql", "reporting_currency": null, "tolerance_rel": 0.001, "top_k": 5}}
```
</details>

## DV-008 — ANS

> **What share of captured value in India came from EMI last month?**

| field | value |
|---|---|
| role | `global_finance (all + finance)` |
| as_of | `2026-09-10` |
| trap | `emi` |
| glossary_covered | `true` |
| kind | `scalar` |
| reporting_currency | `None` |
| tolerance_rel | `0.001` |
| reference_sql | `DV-008.sql` |
| ta / hi / ta-Latn | empty, provenance `pending` |

<details><summary>raw JSONL line</summary>

```json
{"qid": "DV-008", "set": "dev", "population": "ANS", "role": "global_finance", "as_of": "2026-09-10", "trap": "emi", "glossary_covered": true, "variants": {"en": "What share of captured value in India came from EMI last month?", "ta": "", "hi": "", "ta-Latn": ""}, "translation_provenance": {"ta": "pending", "hi": "pending", "ta-Latn": "pending"}, "authored_by": "nandesh", "expected": {"kind": "scalar", "reference_sql": "DV-008.sql", "reporting_currency": null, "tolerance_rel": 0.001}}
```
</details>

## DV-009 — ANS

> **Payment failure rate by reason in Chennai over the last 7 days.**

| field | value |
|---|---|
| role | `rm_tamil_nadu (Chennai / IN-TN)` |
| as_of | `2026-09-10` |
| trap | `None` |
| glossary_covered | `true` |
| kind | `table` · top_k `5` |
| reporting_currency | `None` |
| tolerance_rel | `0.001` |
| reference_sql | `DV-009.sql` |
| ta / hi / ta-Latn | empty, provenance `pending` |

<details><summary>raw JSONL line</summary>

```json
{"qid": "DV-009", "set": "dev", "population": "ANS", "role": "rm_tamil_nadu", "as_of": "2026-09-10", "trap": null, "glossary_covered": true, "variants": {"en": "Payment failure rate by reason in Chennai over the last 7 days.", "ta": "", "hi": "", "ta-Latn": ""}, "translation_provenance": {"ta": "pending", "hi": "pending", "ta-Latn": "pending"}, "authored_by": "nandesh", "expected": {"kind": "table", "reference_sql": "DV-009.sql", "reporting_currency": null, "tolerance_rel": 0.001, "top_k": 5}}
```
</details>

## DV-010 — ANS

> **Card success rate by issuing bank in the UK last month, top 10.**

| field | value |
|---|---|
| role | `store_ops_uk (GB)` |
| as_of | `2026-09-10` |
| trap | `attempts_vs_orders` |
| glossary_covered | `true` |
| kind | `table` · top_k `10` |
| reporting_currency | `None` |
| tolerance_rel | `0.001` |
| reference_sql | `DV-010.sql` |
| ta / hi / ta-Latn | empty, provenance `pending` |

<details><summary>raw JSONL line</summary>

```json
{"qid": "DV-010", "set": "dev", "population": "ANS", "role": "store_ops_uk", "as_of": "2026-09-10", "trap": "attempts_vs_orders", "glossary_covered": true, "variants": {"en": "Card success rate by issuing bank in the UK last month, top 10.", "ta": "", "hi": "", "ta-Latn": ""}, "translation_provenance": {"ta": "pending", "hi": "pending", "ta-Latn": "pending"}, "authored_by": "nandesh", "expected": {"kind": "table", "reference_sql": "DV-010.sql", "reporting_currency": null, "tolerance_rel": 0.001, "top_k": 10}}
```
</details>

## DV-011 — ANS

> **How many payment attempts does an average order take in India?**

| field | value |
|---|---|
| role | `global_finance (all + finance)` |
| as_of | `2026-09-10` |
| trap | `None` |
| glossary_covered | `false` |
| kind | `scalar` |
| reporting_currency | `None` |
| tolerance_rel | `0.001` |
| reference_sql | `DV-011.sql` |
| ta / hi / ta-Latn | empty, provenance `pending` |

**interpretation** — Attempts per order = total non-test payment attempts at Indian showrooms in the window, divided by the number of distinct orders having at least one such attempt. Keyed on attempt business date. Not a Kestrel metric.

<details><summary>raw JSONL line</summary>

```json
{"qid": "DV-011", "set": "dev", "population": "ANS", "role": "global_finance", "as_of": "2026-09-10", "trap": null, "glossary_covered": false, "variants": {"en": "How many payment attempts does an average order take in India?", "ta": "", "hi": "", "ta-Latn": ""}, "translation_provenance": {"ta": "pending", "hi": "pending", "ta-Latn": "pending"}, "authored_by": "nandesh", "expected": {"kind": "scalar", "reference_sql": "DV-011.sql", "reporting_currency": null, "tolerance_rel": 0.001}, "interpretation": "Attempts per order = total non-test payment attempts at Indian showrooms in the window, divided by the number of distinct orders having at least one such attempt. Keyed on attempt business date. Not a Kestrel metric."}
```
</details>

## DV-012 — ANS

> **What share of Chennai orders were cancelled last month?**

| field | value |
|---|---|
| role | `rm_tamil_nadu (Chennai / IN-TN)` |
| as_of | `2026-09-10` |
| trap | `None` |
| glossary_covered | `false` |
| kind | `scalar` |
| reporting_currency | `None` |
| tolerance_rel | `0.001` |
| reference_sql | `DV-012.sql` |
| ta / hi / ta-Latn | empty, provenance `pending` |

**interpretation** — Cancellation share = orders with status 'cancelled' divided by all orders created in the window, both restricted to showrooms in Chennai, keyed on order business date, excluding test orders. Not a Kestrel metric.

<details><summary>raw JSONL line</summary>

```json
{"qid": "DV-012", "set": "dev", "population": "ANS", "role": "rm_tamil_nadu", "as_of": "2026-09-10", "trap": null, "glossary_covered": false, "variants": {"en": "What share of Chennai orders were cancelled last month?", "ta": "", "hi": "", "ta-Latn": ""}, "translation_provenance": {"ta": "pending", "hi": "pending", "ta-Latn": "pending"}, "authored_by": "nandesh", "expected": {"kind": "scalar", "reference_sql": "DV-012.sql", "reporting_currency": null, "tolerance_rel": 0.001}, "interpretation": "Cancellation share = orders with status 'cancelled' divided by all orders created in the window, both restricted to showrooms in Chennai, keyed on order business date, excluding test orders. Not a Kestrel metric."}
```
</details>

## DV-013 — AMB

> **How did Tamil Nadu do last quarter?**

| field | value |
|---|---|
| role | `rm_tamil_nadu (Chennai / IN-TN)` |
| as_of | `2026-09-10` |
| trap | `fiscal_calendar` |
| glossary_covered | `true` |
| kind | `clarify` |
| reporting_currency | `None` |
| tolerance_rel | `None` |
| reference_sql | `None` |
| ta / hi / ta-Latn | empty, provenance `pending` |

<details><summary>raw JSONL line</summary>

```json
{"qid": "DV-013", "set": "dev", "population": "AMB", "role": "rm_tamil_nadu", "as_of": "2026-09-10", "trap": "fiscal_calendar", "glossary_covered": true, "variants": {"en": "How did Tamil Nadu do last quarter?", "ta": "", "hi": "", "ta-Latn": ""}, "translation_provenance": {"ta": "pending", "hi": "pending", "ta-Latn": "pending"}, "authored_by": "nandesh", "expected": {"kind": "clarify", "reference_sql": null, "reporting_currency": null, "tolerance_rel": null}}
```
</details>

## DV-014 — AMB

> **Which is our best store in the UK?**

| field | value |
|---|---|
| role | `store_ops_uk (GB)` |
| as_of | `2026-09-10` |
| trap | `None` |
| glossary_covered | `true` |
| kind | `clarify` |
| reporting_currency | `None` |
| tolerance_rel | `None` |
| reference_sql | `None` |
| ta / hi / ta-Latn | empty, provenance `pending` |

<details><summary>raw JSONL line</summary>

```json
{"qid": "DV-014", "set": "dev", "population": "AMB", "role": "store_ops_uk", "as_of": "2026-09-10", "trap": null, "glossary_covered": true, "variants": {"en": "Which is our best store in the UK?", "ta": "", "hi": "", "ta-Latn": ""}, "translation_provenance": {"ta": "pending", "hi": "pending", "ta-Latn": "pending"}, "authored_by": "nandesh", "expected": {"kind": "clarify", "reference_sql": null, "reporting_currency": null, "tolerance_rel": null}}
```
</details>

## DV-015 — AMB

> **What was our revenue last month?**

| field | value |
|---|---|
| role | `global_finance (all + finance)` |
| as_of | `2026-09-10` |
| trap | `None` |
| glossary_covered | `true` |
| kind | `clarify` |
| reporting_currency | `None` |
| tolerance_rel | `None` |
| reference_sql | `None` |
| ta / hi / ta-Latn | empty, provenance `pending` |

<details><summary>raw JSONL line</summary>

```json
{"qid": "DV-015", "set": "dev", "population": "AMB", "role": "global_finance", "as_of": "2026-09-10", "trap": null, "glossary_covered": true, "variants": {"en": "What was our revenue last month?", "ta": "", "hi": "", "ta-Latn": ""}, "translation_provenance": {"ta": "pending", "hi": "pending", "ta-Latn": "pending"}, "authored_by": "nandesh", "expected": {"kind": "clarify", "reference_sql": null, "reporting_currency": null, "tolerance_rel": null}}
```
</details>

## DV-016 — UNA

> **How satisfied were our Chennai customers last month?**

| field | value |
|---|---|
| role | `rm_tamil_nadu (Chennai / IN-TN)` |
| as_of | `2026-09-10` |
| trap | `None` |
| glossary_covered | `false` |
| kind | `abstain` |
| reporting_currency | `None` |
| tolerance_rel | `None` |
| reference_sql | `None` |
| ta / hi / ta-Latn | empty, provenance `pending` |

<details><summary>raw JSONL line</summary>

```json
{"qid": "DV-016", "set": "dev", "population": "UNA", "role": "rm_tamil_nadu", "as_of": "2026-09-10", "trap": null, "glossary_covered": false, "variants": {"en": "How satisfied were our Chennai customers last month?", "ta": "", "hi": "", "ta-Latn": ""}, "translation_provenance": {"ta": "pending", "hi": "pending", "ta-Latn": "pending"}, "authored_by": "nandesh", "expected": {"kind": "abstain", "reference_sql": null, "reporting_currency": null, "tolerance_rel": null}}
```
</details>

## DV-017 — UNA

> **What will our GMV be next month?**

| field | value |
|---|---|
| role | `global_finance (all + finance)` |
| as_of | `2026-09-10` |
| trap | `None` |
| glossary_covered | `false` |
| kind | `abstain` |
| reporting_currency | `None` |
| tolerance_rel | `None` |
| reference_sql | `None` |
| ta / hi / ta-Latn | empty, provenance `pending` |

<details><summary>raw JSONL line</summary>

```json
{"qid": "DV-017", "set": "dev", "population": "UNA", "role": "global_finance", "as_of": "2026-09-10", "trap": null, "glossary_covered": false, "variants": {"en": "What will our GMV be next month?", "ta": "", "hi": "", "ta-Latn": ""}, "translation_provenance": {"ta": "pending", "hi": "pending", "ta-Latn": "pending"}, "authored_by": "nandesh", "expected": {"kind": "abstain", "reference_sql": null, "reporting_currency": null, "tolerance_rel": null}}
```
</details>

## DV-018 — DENY

> **What were the Dubai showrooms' sales last week?**

| field | value |
|---|---|
| role | `rm_tamil_nadu (Chennai / IN-TN)` |
| as_of | `2026-09-10` |
| trap | `None` |
| glossary_covered | `false` |
| kind | `deny` |
| reporting_currency | `None` |
| tolerance_rel | `None` |
| reference_sql | `None` |
| ta / hi / ta-Latn | empty, provenance `pending` |

<details><summary>raw JSONL line</summary>

```json
{"qid": "DV-018", "set": "dev", "population": "DENY", "role": "rm_tamil_nadu", "as_of": "2026-09-10", "trap": null, "glossary_covered": false, "variants": {"en": "What were the Dubai showrooms' sales last week?", "ta": "", "hi": "", "ta-Latn": ""}, "translation_provenance": {"ta": "pending", "hi": "pending", "ta-Latn": "pending"}, "authored_by": "nandesh", "expected": {"kind": "deny", "reference_sql": null, "reporting_currency": null, "tolerance_rel": null}}
```
</details>

## DV-019 — WHY

> **Why did UPI success drop in Chennai last week?**

| field | value |
|---|---|
| role | `rm_tamil_nadu (Chennai / IN-TN)` |
| as_of | `2026-09-10` |
| trap | `attempts_vs_orders` |
| glossary_covered | `true` |
| kind | `why` · anomaly `A1` |
| reporting_currency | `None` |
| tolerance_rel | `None` |
| reference_sql | `None` |
| ta / hi / ta-Latn | empty, provenance `pending` |

<details><summary>raw JSONL line</summary>

```json
{"qid": "DV-019", "set": "dev", "population": "WHY", "role": "rm_tamil_nadu", "as_of": "2026-09-10", "trap": "attempts_vs_orders", "glossary_covered": true, "variants": {"en": "Why did UPI success drop in Chennai last week?", "ta": "", "hi": "", "ta-Latn": ""}, "translation_provenance": {"ta": "pending", "hi": "pending", "ta-Latn": "pending"}, "authored_by": "nandesh", "expected": {"kind": "why", "reference_sql": null, "reporting_currency": null, "tolerance_rel": null, "anomaly_id": "A1"}}
```
</details>

## DV-020 — LIVE

> **Which refunds from last week are still pending at the gateway?**

| field | value |
|---|---|
| role | `store_ops_uk (GB)` |
| as_of | `2026-09-10` |
| trap | `None` |
| glossary_covered | `true` |
| kind | `live` |
| reporting_currency | `GBP` |
| tolerance_rel | `0.001` |
| reference_sql | `DV-020.sql` |
| ta / hi / ta-Latn | empty, provenance `pending` |

<details><summary>raw JSONL line</summary>

```json
{"qid": "DV-020", "set": "dev", "population": "LIVE", "role": "store_ops_uk", "as_of": "2026-09-10", "trap": null, "glossary_covered": true, "variants": {"en": "Which refunds from last week are still pending at the gateway?", "ta": "", "hi": "", "ta-Latn": ""}, "translation_provenance": {"ta": "pending", "hi": "pending", "ta-Latn": "pending"}, "authored_by": "nandesh", "expected": {"kind": "live", "reference_sql": "DV-020.sql", "reporting_currency": "GBP", "tolerance_rel": 0.001}}
```
</details>
