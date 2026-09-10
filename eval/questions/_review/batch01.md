# Batch 01 — dev.jsonl, DV-001–DV-020

**File:** `eval/questions/dev.jsonl` (lines 1–20)  
**Status:** draft, awaiting approval. This review file is deleted at `questions-frozen`.

## What changed since your review

- **DV-002 duplicate:** paste artifact. The file has 20 lines, no duplicate qids,
  and DV-002 carries its own role and text. No change made.
- **DV-004** — "collect" kept, and `GLOSSARY.md` §5 now maps *collected / took /
  brought in / made* → captured GMV, explicitly **not** settled money. The word
  now resolves to one metric, so the question stays ANS.
- **DV-007** — `GLOSSARY.md` §2.2 now states outright that units **include
  accessories**, with the consequence spelled out (units > handsets; an
  accessory-heavy showroom ranks higher on units than on phones).
- **DV-010** — new `GLOSSARY.md` §1.9: an order is attributed to the method,
  network and issuing bank of its **final attempt**. Applied to every order-level
  per-bank/per-method breakdown, so per-bank rates reconcile to the overall rate.
- **DV-011, DV-012** — kept in ANS, each now carries an `interpretation` sentence
  that M3's reference SQL must follow.
- **DV-019** — window added: "last week" = `2026-08-31 … 2026-09-06`. Recorded in
  `docs/M2_NOTES.md` as a binding constraint on where A1 is planted.
- **"Success rate"** unchanged: order-level per §4.1.
- **"Revenue"** stays ambiguous, now formalised in new `GLOSSARY.md` §6 —
  §6.1 lists terms with an official default (answer and disclose), §6.2 lists
  terms that must be clarified (revenue, best/top/worst, unqualified quarter,
  performance/growth).

## Batch summary

- Populations: AMB 3 · ANS 12 · DENY 1 · LIVE 1 · UNA 2 · WHY 1
- Roles: global_finance 6 · rm_tamil_nadu 9 · store_ops_uk 5
- `glossary_covered: false`: 5/20 = 25%
- Traps touched: attempts_vs_orders 3 · authorised_vs_captured 1 · capture_vs_settlement 1 · emi 1 · fiscal_calendar 1 · local_time 1 · multi_currency 1 · partial_refunds 1

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

> **Payment failures by reason in Chennai over the last 7 days.**

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
{"qid": "DV-009", "set": "dev", "population": "ANS", "role": "rm_tamil_nadu", "as_of": "2026-09-10", "trap": null, "glossary_covered": true, "variants": {"en": "Payment failures by reason in Chennai over the last 7 days.", "ta": "", "hi": "", "ta-Latn": ""}, "translation_provenance": {"ta": "pending", "hi": "pending", "ta-Latn": "pending"}, "authored_by": "nandesh", "expected": {"kind": "table", "reference_sql": "DV-009.sql", "reporting_currency": null, "tolerance_rel": 0.001, "top_k": 5}}
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
