---
title: Receipts — Kestrel Mobile
emoji: 🧾
colorFrom: indigo
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
short_description: A payments analytics agent where every answer carries a receipt
---

# Receipts

Ask a question about payments in **English, Tamil or Hindi**. The model produces
a typed query plan over a governed semantic layer, a deterministic compiler
writes the SQL, and every answer carries a **receipt**: the metric's definition,
the window, the scope, what was excluded, and the hashes of the plan and the SQL
that produced the number.

**Try it as a role** — the scope is compiled into the SQL, not asked for politely:

- [Chennai regional manager](?role=rm_tamil_nadu) — sees Tamil Nadu only
- [Global finance](?role=global_finance) — sees everything, holds the finance capability
- [UK store ops](?role=store_ops_uk) — sees the UK, reports in GBP
- [Admin](?role=admin)

Ask the Chennai manager about Dubai and watch it refuse. Ask UK store ops about
settlement fees and watch the capability check bite.

## This demo answers a fixed set of recorded questions

It runs in **replay mode**: the model responses are the ones recorded when the
evaluation ran, committed to the repository and served from disk. No model is
called, nothing is spent per question, and the answers are exactly the ones that
were measured. Each role's example questions are generated from that recorded
set, so they always work; a question outside it says so plainly.

The data is synthetic. Kestrel Mobile is fictional.

Source: https://github.com/nandeshkanagaraju/receipts
