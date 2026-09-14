# Receipts

**The thesis failed.** On 91 held-out questions the pre-declared test — Receipts'
silent-wrong rate at most half the baseline's (T2 ≤ 0.5) — came out at **0.733**,
and conditional on answering, Receipts was **worse** than the baseline: 36.7%
silently wrong against 33.3%.

In the project's own pre-written words, chosen before any result was seen
(PDD §12):

> *A strong baseline given the same metric definitions was about as safe as the
> constrained pipeline. The definitions did the work, not the architecture. The
> remaining case for Receipts is governance (scoping, audit, receipts) rather
> than accuracy, and we report it on those terms.*

| holdout, English, 91 trials | Receipts | baseline |
|---|---:|---:|
| coverage (ANS correct) | 14/45 = **31.1%** | 29/45 = 64.4% |
| silent-wrong, raw | 11/45 = **24.4%** | 15/45 = 33.3% |
| silent-wrong given it answered | 11/30 = **36.7%** | 15/45 = 33.3% |
| declined to answer | 15/45 = 33.3% | 0/45 |

Receipts' lower raw rate comes entirely from declining a third of the questions.
Four pre-declared thresholds failed: T1 (silent-wrong ≤ 3%), T2 (≤ 0.5),
T3 (accuracy ≥ 85%), T5 (over-abstention ≤ 10%).

Every number above is in
[`eval/results/holdout/`](eval/results/holdout/), written by one run at commit
`dd5227a`, on `openai/gpt-5.5-2026-04-23`. The holdout ran **once**; a second run
of either arm is refused by `eval/results/holdout/LOCK` (D17, ADR-023).

## What did survive

**Scope.** On the six questions that ask for data outside the asker's region,
Receipts refused **5 of 6** correctly. The baseline got **0 of 6**.

The difference is structural. Receipts' scope is a predicate the compiler welds
into the SQL from the role, after the plan exists — the model is never told which
regions the asker may see and cannot put a scope in a plan, because `QueryPlan`
has no scope field. The baseline's scope is a paragraph of English in a prompt.
One is enforced; the other is requested.

That is the governance claim, and it is the one the measurement supports.

## The finding that matters most

**The gap between dev and holdout is the size of the memory dev carries.**

On dev, Receipts scored 71.3% coverage and 11.1% silent-wrong. On the holdout,
31.1% and 24.4%. Dev is the set six diagnostic rounds ran against. Every fix in
those rounds implemented a rule written down *before* the failure was seen — the
glossary, the SDD — and each was verified against hand-written reference SQL
rather than against the scorer. None of that was cheating, and it still did not
transfer.

A development set that has been looked at six times is not a measurement. It is
a memory of six rounds of looking, and the only way to find out how much of the
number was memory was to spend it on questions nobody had seen.

## What this project is

A payments-analytics agent for a fictional phone retailer. Questions arrive in
English, Tamil, Hindi or Tanglish; a model produces a typed `QueryPlan` over a
governed semantic layer; a deterministic compiler writes the SQL; **every answer
carries a receipt** naming the metric, its definition, the window, the scope,
what was excluded, and the hashes of the plan and the SQL.

The model never writes SQL on the verified path. When it does — the free-form
fallback — the answer returns `UNVERIFIED` and says so.

![Pipeline](docs/diagrams/receipts_agent_pipeline.png)

![Architecture](docs/diagrams/receipts_platform_architecture.png)

### The measurement machinery

The point of the machinery is that a result like the one above can be trusted to
be the result.

- **Thresholds were pre-declared** in `config/thresholds.yaml` at G0, before any
  engine code existed, and are frozen.
- **Two systems, one harness.** The baseline (B0) gets the same questions, the
  same metric definitions and the same model. It is not a straw man: it beat
  Receipts on coverage.
- **Answers are compared against hand-written reference SQL**, not against the
  scorer's opinion.
- **Every model call is recorded and replayed.** Two consecutive replays of a run
  produce byte-identical reports (D16), so a published number can be reproduced
  from the repository.
- **The holdout runs once**, behind a lock recording the system, the language set
  and the commit.
- **No clock reads in engine packages** (D2), deterministic IDs only (D3), money
  as integer minor units (D1) — each enforced by a charter test that walks the
  AST rather than grepping.

1,282 tests. `LIMITATIONS.md` is the list of everything this project cannot
claim, including the three errors I made in the round that produced the result above.

### Cost

Measured over the same 30 questions through the same meter
([`eval/results/bench.json`](eval/results/bench.json)):
**Receipts $36.20 per 1,000 questions, baseline $99.28** — the baseline puts the
whole schema in the prompt (16,160 median input tokens against 3,625).

## Try it

**Live demo:** http://ec2-13-204-169-218.ap-south-1.compute.amazonaws.com/?role=rm_tamil_nadu

Answers are replayed from the recorded evaluation, so they are exactly the ones
that were measured. Switch role in the header and ask the Chennai manager about
Dubai.

```bash
make data     # generate the synthetic warehouse (~3.5 min)
make up       # API, SPA and MCP in one container, at :8000
make eval     # re-run a scored evaluation and diff it against the committed one
```

`make bench` reports latency per stage and cost per 1,000 questions.
`make web-e2e` runs the browser journeys.

The MCP server is mounted inside the API at `/mcp`; setup for Claude Desktop is
in [`docs/MCP.md`](docs/MCP.md). The token decides what you can see and nothing
else does — scope is recomputed from `config/roles.yaml` on every call.

All data is synthetic. Kestrel Mobile is fictional.
