# Batch 02 — dev.jsonl, DV-021–DV-040

**File:** `eval/questions/dev.jsonl` (lines 21–40)  
**Status:** draft, awaiting approval. This review file is deleted at `questions-frozen`.

## Notes on this batch

- Completes trap coverage: `duplicate_captures` (DV-022) and `test_transactions`
  (DV-023) were the two untouched after batch 1.
- **DV-028** asks for attempt-level success explicitly, as the deliberate
  counterpart to DV-001's unqualified (order-level) phrasing. Same region, same
  metric family, different number — the pair is the attempts-vs-orders trap made
  visible in the eval itself.
- **DV-032** and **DV-033** are the `glossary_covered: false` questions here, both
  with `interpretation`. Authorised-not-captured is computable but not a Kestrel
  metric; distinct-bank-count likewise.
- **DV-039** is the mirror of DV-018: a UK role asking about Chennai. Both
  directions of denial are now covered, so DENY cannot be passed by a rule that
  only ever refuses one region.
- **DV-040** names A5 with window "last month" = `2026-08-01 … 2026-08-31`, also
  recorded in `docs/M2_NOTES.md`.

## Batch summary

- Populations: AMB 3 · ANS 13 · DENY 1 · UNA 2 · WHY 1
- Roles: global_finance 7 · rm_tamil_nadu 5 · store_ops_uk 8
- `glossary_covered: false`: 5/20 = 25%
- Traps touched: attempts_vs_orders 1 · authorised_vs_captured 1 · capture_vs_settlement 1 · duplicate_captures 1 · emi 1 · fiscal_calendar 1 · local_time 1 · partial_refunds 2 · test_transactions 1

---

## DV-021 — ANS

> **Net revenue across all countries in August, in US dollars.**

| field | value |
|---|---|
| role | `global_finance (all + finance)` |
| as_of | `2026-09-10` |
| trap | `partial_refunds` |
| glossary_covered | `true` |
| kind | `scalar` |
| reporting_currency | `USD` |
| tolerance_rel | `0.001` |
| reference_sql | `DV-021.sql` |
| ta / hi / ta-Latn | empty, provenance `pending` |

<details><summary>raw JSONL line</summary>

```json
{"qid": "DV-021", "set": "dev", "population": "ANS", "role": "global_finance", "as_of": "2026-09-10", "trap": "partial_refunds", "glossary_covered": true, "variants": {"en": "Net revenue across all countries in August, in US dollars.", "ta": "", "hi": "", "ta-Latn": ""}, "translation_provenance": {"ta": "pending", "hi": "pending", "ta-Latn": "pending"}, "authored_by": "nandesh", "expected": {"kind": "scalar", "reference_sql": "DV-021.sql", "reporting_currency": "USD", "tolerance_rel": 0.001}}
```
</details>

## DV-022 — ANS

> **How many duplicate captures were there in Tamil Nadu last month?**

| field | value |
|---|---|
| role | `rm_tamil_nadu (Chennai / IN-TN)` |
| as_of | `2026-09-10` |
| trap | `duplicate_captures` |
| glossary_covered | `true` |
| kind | `scalar` |
| reporting_currency | `None` |
| tolerance_rel | `0.001` |
| reference_sql | `DV-022.sql` |
| ta / hi / ta-Latn | empty, provenance `pending` |

<details><summary>raw JSONL line</summary>

```json
{"qid": "DV-022", "set": "dev", "population": "ANS", "role": "rm_tamil_nadu", "as_of": "2026-09-10", "trap": "duplicate_captures", "glossary_covered": true, "variants": {"en": "How many duplicate captures were there in Tamil Nadu last month?", "ta": "", "hi": "", "ta-Latn": ""}, "translation_provenance": {"ta": "pending", "hi": "pending", "ta-Latn": "pending"}, "authored_by": "nandesh", "expected": {"kind": "scalar", "reference_sql": "DV-022.sql", "reporting_currency": null, "tolerance_rel": 0.001}}
```
</details>

## DV-023 — ANS

> **How many payment attempts did we take in Singapore last month?**

| field | value |
|---|---|
| role | `global_finance (all + finance)` |
| as_of | `2026-09-10` |
| trap | `test_transactions` |
| glossary_covered | `true` |
| kind | `scalar` |
| reporting_currency | `None` |
| tolerance_rel | `0.001` |
| reference_sql | `DV-023.sql` |
| ta / hi / ta-Latn | empty, provenance `pending` |

<details><summary>raw JSONL line</summary>

```json
{"qid": "DV-023", "set": "dev", "population": "ANS", "role": "global_finance", "as_of": "2026-09-10", "trap": "test_transactions", "glossary_covered": true, "variants": {"en": "How many payment attempts did we take in Singapore last month?", "ta": "", "hi": "", "ta-Latn": ""}, "translation_provenance": {"ta": "pending", "hi": "pending", "ta-Latn": "pending"}, "authored_by": "nandesh", "expected": {"kind": "scalar", "reference_sql": "DV-023.sql", "reporting_currency": null, "tolerance_rel": 0.001}}
```
</details>

## DV-024 — ANS

> **What was our average order value in the UK last month?**

| field | value |
|---|---|
| role | `store_ops_uk (GB)` |
| as_of | `2026-09-10` |
| trap | `None` |
| glossary_covered | `true` |
| kind | `scalar` |
| reporting_currency | `GBP` |
| tolerance_rel | `0.001` |
| reference_sql | `DV-024.sql` |
| ta / hi / ta-Latn | empty, provenance `pending` |

<details><summary>raw JSONL line</summary>

```json
{"qid": "DV-024", "set": "dev", "population": "ANS", "role": "store_ops_uk", "as_of": "2026-09-10", "trap": null, "glossary_covered": true, "variants": {"en": "What was our average order value in the UK last month?", "ta": "", "hi": "", "ta-Latn": ""}, "translation_provenance": {"ta": "pending", "hi": "pending", "ta-Latn": "pending"}, "authored_by": "nandesh", "expected": {"kind": "scalar", "reference_sql": "DV-024.sql", "reporting_currency": "GBP", "tolerance_rel": 0.001}}
```
</details>

## DV-025 — ANS

> **EMI share by city in Tamil Nadu last month, top 5.**

| field | value |
|---|---|
| role | `rm_tamil_nadu (Chennai / IN-TN)` |
| as_of | `2026-09-10` |
| trap | `emi` |
| glossary_covered | `true` |
| kind | `table` · top_k `5` |
| reporting_currency | `None` |
| tolerance_rel | `0.001` |
| reference_sql | `DV-025.sql` |
| ta / hi / ta-Latn | empty, provenance `pending` |

<details><summary>raw JSONL line</summary>

```json
{"qid": "DV-025", "set": "dev", "population": "ANS", "role": "rm_tamil_nadu", "as_of": "2026-09-10", "trap": "emi", "glossary_covered": true, "variants": {"en": "EMI share by city in Tamil Nadu last month, top 5.", "ta": "", "hi": "", "ta-Latn": ""}, "translation_provenance": {"ta": "pending", "hi": "pending", "ta-Latn": "pending"}, "authored_by": "nandesh", "expected": {"kind": "table", "reference_sql": "DV-025.sql", "reporting_currency": null, "tolerance_rel": 0.001, "top_k": 5}}
```
</details>

## DV-026 — ANS

> **How much captured money was still unsettled at the end of August?**

| field | value |
|---|---|
| role | `global_finance (all + finance)` |
| as_of | `2026-09-10` |
| trap | `capture_vs_settlement` |
| glossary_covered | `true` |
| kind | `scalar` |
| reporting_currency | `USD` |
| tolerance_rel | `0.001` |
| reference_sql | `DV-026.sql` |
| ta / hi / ta-Latn | empty, provenance `pending` |

<details><summary>raw JSONL line</summary>

```json
{"qid": "DV-026", "set": "dev", "population": "ANS", "role": "global_finance", "as_of": "2026-09-10", "trap": "capture_vs_settlement", "glossary_covered": true, "variants": {"en": "How much captured money was still unsettled at the end of August?", "ta": "", "hi": "", "ta-Latn": ""}, "translation_provenance": {"ta": "pending", "hi": "pending", "ta-Latn": "pending"}, "authored_by": "nandesh", "expected": {"kind": "scalar", "reference_sql": "DV-026.sql", "reporting_currency": "USD", "tolerance_rel": 0.001}}
```
</details>

## DV-027 — ANS

> **How many orders did UK showrooms take yesterday?**

| field | value |
|---|---|
| role | `store_ops_uk (GB)` |
| as_of | `2026-09-10` |
| trap | `local_time` |
| glossary_covered | `true` |
| kind | `scalar` |
| reporting_currency | `None` |
| tolerance_rel | `0.001` |
| reference_sql | `DV-027.sql` |
| ta / hi / ta-Latn | empty, provenance `pending` |

<details><summary>raw JSONL line</summary>

```json
{"qid": "DV-027", "set": "dev", "population": "ANS", "role": "store_ops_uk", "as_of": "2026-09-10", "trap": "local_time", "glossary_covered": true, "variants": {"en": "How many orders did UK showrooms take yesterday?", "ta": "", "hi": "", "ta-Latn": ""}, "translation_provenance": {"ta": "pending", "hi": "pending", "ta-Latn": "pending"}, "authored_by": "nandesh", "expected": {"kind": "scalar", "reference_sql": "DV-027.sql", "reporting_currency": null, "tolerance_rel": 0.001}}
```
</details>

## DV-028 — ANS

> **What was the attempt-level UPI success rate in Chennai last week?**

| field | value |
|---|---|
| role | `rm_tamil_nadu (Chennai / IN-TN)` |
| as_of | `2026-09-10` |
| trap | `attempts_vs_orders` |
| glossary_covered | `true` |
| kind | `scalar` |
| reporting_currency | `None` |
| tolerance_rel | `0.001` |
| reference_sql | `DV-028.sql` |
| ta / hi / ta-Latn | empty, provenance `pending` |

<details><summary>raw JSONL line</summary>

```json
{"qid": "DV-028", "set": "dev", "population": "ANS", "role": "rm_tamil_nadu", "as_of": "2026-09-10", "trap": "attempts_vs_orders", "glossary_covered": true, "variants": {"en": "What was the attempt-level UPI success rate in Chennai last week?", "ta": "", "hi": "", "ta-Latn": ""}, "translation_provenance": {"ta": "pending", "hi": "pending", "ta-Latn": "pending"}, "authored_by": "nandesh", "expected": {"kind": "scalar", "reference_sql": "DV-028.sql", "reporting_currency": null, "tolerance_rel": 0.001}}
```
</details>

## DV-029 — ANS

> **Top 10 phone models by units sold last month.**

| field | value |
|---|---|
| role | `global_finance (all + finance)` |
| as_of | `2026-09-10` |
| trap | `None` |
| glossary_covered | `true` |
| kind | `table` · top_k `10` |
| reporting_currency | `None` |
| tolerance_rel | `0.001` |
| reference_sql | `DV-029.sql` |
| ta / hi / ta-Latn | empty, provenance `pending` |

<details><summary>raw JSONL line</summary>

```json
{"qid": "DV-029", "set": "dev", "population": "ANS", "role": "global_finance", "as_of": "2026-09-10", "trap": null, "glossary_covered": true, "variants": {"en": "Top 10 phone models by units sold last month.", "ta": "", "hi": "", "ta-Latn": ""}, "translation_provenance": {"ta": "pending", "hi": "pending", "ta-Latn": "pending"}, "authored_by": "nandesh", "expected": {"kind": "table", "reference_sql": "DV-029.sql", "reporting_currency": null, "tolerance_rel": 0.001, "top_k": 10}}
```
</details>

## DV-030 — ANS

> **How much did we refund in the UK last month?**

| field | value |
|---|---|
| role | `store_ops_uk (GB)` |
| as_of | `2026-09-10` |
| trap | `partial_refunds` |
| glossary_covered | `true` |
| kind | `scalar` |
| reporting_currency | `GBP` |
| tolerance_rel | `0.001` |
| reference_sql | `DV-030.sql` |
| ta / hi / ta-Latn | empty, provenance `pending` |

<details><summary>raw JSONL line</summary>

```json
{"qid": "DV-030", "set": "dev", "population": "ANS", "role": "store_ops_uk", "as_of": "2026-09-10", "trap": "partial_refunds", "glossary_covered": true, "variants": {"en": "How much did we refund in the UK last month?", "ta": "", "hi": "", "ta-Latn": ""}, "translation_provenance": {"ta": "pending", "hi": "pending", "ta-Latn": "pending"}, "authored_by": "nandesh", "expected": {"kind": "scalar", "reference_sql": "DV-030.sql", "reporting_currency": "GBP", "tolerance_rel": 0.001}}
```
</details>

## DV-031 — ANS

> **Accessory attach rate by showroom in Chennai last month, top 5.**

| field | value |
|---|---|
| role | `rm_tamil_nadu (Chennai / IN-TN)` |
| as_of | `2026-09-10` |
| trap | `None` |
| glossary_covered | `true` |
| kind | `table` · top_k `5` |
| reporting_currency | `None` |
| tolerance_rel | `0.001` |
| reference_sql | `DV-031.sql` |
| ta / hi / ta-Latn | empty, provenance `pending` |

<details><summary>raw JSONL line</summary>

```json
{"qid": "DV-031", "set": "dev", "population": "ANS", "role": "rm_tamil_nadu", "as_of": "2026-09-10", "trap": null, "glossary_covered": true, "variants": {"en": "Accessory attach rate by showroom in Chennai last month, top 5.", "ta": "", "hi": "", "ta-Latn": ""}, "translation_provenance": {"ta": "pending", "hi": "pending", "ta-Latn": "pending"}, "authored_by": "nandesh", "expected": {"kind": "table", "reference_sql": "DV-031.sql", "reporting_currency": null, "tolerance_rel": 0.001, "top_k": 5}}
```
</details>

## DV-032 — ANS

> **How much did we authorise but never capture in August?**

| field | value |
|---|---|
| role | `global_finance (all + finance)` |
| as_of | `2026-09-10` |
| trap | `authorised_vs_captured` |
| glossary_covered | `false` |
| kind | `scalar` |
| reporting_currency | `USD` |
| tolerance_rel | `0.001` |
| reference_sql | `DV-032.sql` |
| ta / hi / ta-Latn | empty, provenance `pending` |

**interpretation** — Authorised-not-captured value = sum of amounts on non-test payment attempts that reached authorised status where no attempt on the same order was captured. Keyed on attempt business date, converted to USD at each attempt's own daily rate. Not a Kestrel metric.

<details><summary>raw JSONL line</summary>

```json
{"qid": "DV-032", "set": "dev", "population": "ANS", "role": "global_finance", "as_of": "2026-09-10", "trap": "authorised_vs_captured", "glossary_covered": false, "variants": {"en": "How much did we authorise but never capture in August?", "ta": "", "hi": "", "ta-Latn": ""}, "translation_provenance": {"ta": "pending", "hi": "pending", "ta-Latn": "pending"}, "authored_by": "nandesh", "expected": {"kind": "scalar", "reference_sql": "DV-032.sql", "reporting_currency": "USD", "tolerance_rel": 0.001}, "interpretation": "Authorised-not-captured value = sum of amounts on non-test payment attempts that reached authorised status where no attempt on the same order was captured. Keyed on attempt business date, converted to USD at each attempt's own daily rate. Not a Kestrel metric."}
```
</details>

## DV-033 — ANS

> **How many different issuing banks did we see in the UK last month?**

| field | value |
|---|---|
| role | `store_ops_uk (GB)` |
| as_of | `2026-09-10` |
| trap | `None` |
| glossary_covered | `false` |
| kind | `scalar` |
| reporting_currency | `None` |
| tolerance_rel | `0.001` |
| reference_sql | `DV-033.sql` |
| ta / hi / ta-Latn | empty, provenance `pending` |

**interpretation** — Distinct issuing bank count = number of distinct non-null issuing_bank values on non-test payment attempts at UK showrooms in the window, keyed on attempt business date. Not a Kestrel metric.

<details><summary>raw JSONL line</summary>

```json
{"qid": "DV-033", "set": "dev", "population": "ANS", "role": "store_ops_uk", "as_of": "2026-09-10", "trap": null, "glossary_covered": false, "variants": {"en": "How many different issuing banks did we see in the UK last month?", "ta": "", "hi": "", "ta-Latn": ""}, "translation_provenance": {"ta": "pending", "hi": "pending", "ta-Latn": "pending"}, "authored_by": "nandesh", "expected": {"kind": "scalar", "reference_sql": "DV-033.sql", "reporting_currency": null, "tolerance_rel": 0.001}, "interpretation": "Distinct issuing bank count = number of distinct non-null issuing_bank values on non-test payment attempts at UK showrooms in the window, keyed on attempt business date. Not a Kestrel metric."}
```
</details>

## DV-034 — AMB

> **Show me the Q2 numbers for Tamil Nadu.**

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
{"qid": "DV-034", "set": "dev", "population": "AMB", "role": "rm_tamil_nadu", "as_of": "2026-09-10", "trap": "fiscal_calendar", "glossary_covered": true, "variants": {"en": "Show me the Q2 numbers for Tamil Nadu.", "ta": "", "hi": "", "ta-Latn": ""}, "translation_provenance": {"ta": "pending", "hi": "pending", "ta-Latn": "pending"}, "authored_by": "nandesh", "expected": {"kind": "clarify", "reference_sql": null, "reporting_currency": null, "tolerance_rel": null}}
```
</details>

## DV-035 — AMB

> **Which phone model performed best in the UK last month?**

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
{"qid": "DV-035", "set": "dev", "population": "AMB", "role": "store_ops_uk", "as_of": "2026-09-10", "trap": null, "glossary_covered": true, "variants": {"en": "Which phone model performed best in the UK last month?", "ta": "", "hi": "", "ta-Latn": ""}, "translation_provenance": {"ta": "pending", "hi": "pending", "ta-Latn": "pending"}, "authored_by": "nandesh", "expected": {"kind": "clarify", "reference_sql": null, "reporting_currency": null, "tolerance_rel": null}}
```
</details>

## DV-036 — AMB

> **How are payments doing this month?**

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
{"qid": "DV-036", "set": "dev", "population": "AMB", "role": "global_finance", "as_of": "2026-09-10", "trap": null, "glossary_covered": true, "variants": {"en": "How are payments doing this month?", "ta": "", "hi": "", "ta-Latn": ""}, "translation_provenance": {"ta": "pending", "hi": "pending", "ta-Latn": "pending"}, "authored_by": "nandesh", "expected": {"kind": "clarify", "reference_sql": null, "reporting_currency": null, "tolerance_rel": null}}
```
</details>

## DV-037 — UNA

> **How many staff were working in our Manchester store last week?**

| field | value |
|---|---|
| role | `store_ops_uk (GB)` |
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
{"qid": "DV-037", "set": "dev", "population": "UNA", "role": "store_ops_uk", "as_of": "2026-09-10", "trap": null, "glossary_covered": false, "variants": {"en": "How many staff were working in our Manchester store last week?", "ta": "", "hi": "", "ta-Latn": ""}, "translation_provenance": {"ta": "pending", "hi": "pending", "ta-Latn": "pending"}, "authored_by": "nandesh", "expected": {"kind": "abstain", "reference_sql": null, "reporting_currency": null, "tolerance_rel": null}}
```
</details>

## DV-038 — UNA

> **What is our profit margin on the flagship model?**

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
{"qid": "DV-038", "set": "dev", "population": "UNA", "role": "global_finance", "as_of": "2026-09-10", "trap": null, "glossary_covered": false, "variants": {"en": "What is our profit margin on the flagship model?", "ta": "", "hi": "", "ta-Latn": ""}, "translation_provenance": {"ta": "pending", "hi": "pending", "ta-Latn": "pending"}, "authored_by": "nandesh", "expected": {"kind": "abstain", "reference_sql": null, "reporting_currency": null, "tolerance_rel": null}}
```
</details>

## DV-039 — DENY

> **Show me the Chennai showrooms' refund rate last month.**

| field | value |
|---|---|
| role | `store_ops_uk (GB)` |
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
{"qid": "DV-039", "set": "dev", "population": "DENY", "role": "store_ops_uk", "as_of": "2026-09-10", "trap": null, "glossary_covered": false, "variants": {"en": "Show me the Chennai showrooms' refund rate last month.", "ta": "", "hi": "", "ta-Latn": ""}, "translation_provenance": {"ta": "pending", "hi": "pending", "ta-Latn": "pending"}, "authored_by": "nandesh", "expected": {"kind": "deny", "reference_sql": null, "reporting_currency": null, "tolerance_rel": null}}
```
</details>

## DV-040 — WHY

> **Why did card failures jump in the UK last month?**

| field | value |
|---|---|
| role | `store_ops_uk (GB)` |
| as_of | `2026-09-10` |
| trap | `None` |
| glossary_covered | `true` |
| kind | `why` · anomaly `A5` |
| reporting_currency | `None` |
| tolerance_rel | `None` |
| reference_sql | `None` |
| ta / hi / ta-Latn | empty, provenance `pending` |

<details><summary>raw JSONL line</summary>

```json
{"qid": "DV-040", "set": "dev", "population": "WHY", "role": "store_ops_uk", "as_of": "2026-09-10", "trap": null, "glossary_covered": true, "variants": {"en": "Why did card failures jump in the UK last month?", "ta": "", "hi": "", "ta-Latn": ""}, "translation_provenance": {"ta": "pending", "hi": "pending", "ta-Latn": "pending"}, "authored_by": "nandesh", "expected": {"kind": "why", "reference_sql": null, "reporting_currency": null, "tolerance_rel": null, "anomaly_id": "A5"}}
```
</details>
