# M2 generator — constraints inherited from M1

Notes recorded during M1, binding on the generator. The question sets are frozen
**before** the generator runs (PDD §5), so where a question names a window, the
generator must plant the anomaly inside it. The dependency runs question →
generator, never the reverse.

Reporting date is `2026-09-10` (a Thursday). Data covers `2025-03-01` to
`2026-09-09`.

## 1. Anomaly windows named by frozen questions

Each dev/eval WHY question names a window relative to `as_of`. The planted
anomaly must fall inside it, or the question is unanswerable and the WHY
population scores zero through no fault of the agent.

| Anomaly | What it is (PDD §7) | Must be planted within | Named by |
|---|---|---|---|
| A1 | UPI success dip, one issuing bank, Tamil Nadu, one date | `2026-08-31` … `2026-09-06` (last complete Mon–Sun week) | DV-019 |
| A5 | Card decline spike in the UK after an authentication change | `2026-08-01` … `2026-08-31` (last calendar month) | DV-040 |

A2, A3, A4 and A6 are not yet pinned by a frozen question. Their windows are
fixed as the remaining eval WHY questions are written; this table is updated in
the same commit, and it must be complete before the generator is frozen at G1.

## 2. Sealed anomalies S1–S4

Types are known now and are public. **Parameters — network, country, model, city,
showroom, region, dates, magnitude — are drawn from the sealed seed in M2 and
written only to `eval/sealed/`.** The author does not open that directory before
G5; `test_sealed_read_only_by_scoring` enforces that only `evalkit.scoring` reads
it.

| Id | Type |
|---|---|
| S1 | Card success-rate dip for one card network in one country, lasting a few days |
| S2 | Refund-rate spike on one phone model in one city |
| S3 | Order-volume drop at a single showroom for one week |
| S4 | EMI share **rising** in one region after a promotion |

S4 moves upward deliberately. A why-agent that assumes "explain the drop" will
miss it, and that is a real failure mode worth measuring.

## 3. Holdout WHY questions are generated, not written

The generator writes **six** questions to `eval/sealed/holdout_why.jsonl`:

| From | Count | Phrasing |
|---|---|---|
| S1 | 2 | Once scoped to the affected country, once global |
| S2 | 2 | Once scoped to the affected country, once global |
| S3 | 1 | Country-level |
| S4 | 1 | Region's country level |

Each question names **only the metric, the country, and the week**. It must never
name the card network, phone model, city, showroom, issuing bank, or size — those
are the answer the why-agent is being scored on finding.

The generated rows follow the same schema as the hand-written files, with
`set: "holdout"`, `population: "WHY"`, `authored_by: "kestrel_gen"`,
`expected.kind: "why"`, and `expected.anomaly_id` set to `S1`…`S4`.
`evalkit.questions` loads them for the **holdout set only**.

Qids are `HO-W01` … `HO-W06`, assigned in the order above so they are stable
across regenerations with the same seed (D3: deterministic, ordered counters).

## 4. Population arithmetic for the holdout set

| Source | Count | Populations |
|---|---|---|
| `eval/questions/holdout.jsonl` (hand-written) | 54 | ANS 32 · AMB 7 · UNA 6 · DENY 6 · LIVE 3 |
| Blind author (`holdout_blind_TODO.md`) | 30 | ANS 22 · AMB 5 · UNA 3 |
| Generated (`eval/sealed/holdout_why.jsonl`) | 6 | WHY 6 |
| **Total** | **90** | ANS 54 · AMB 12 · UNA 9 · DENY 6 · WHY 6 · LIVE 3 |

The totals match SDD §25.2 exactly. Only the authorship is split.
