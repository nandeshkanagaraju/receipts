# ADR-018: OpenAI on both sides, a dated snapshot, and no second opinion

**Status** Accepted
**Date** 2026-09-12

## Context

SDD §4 names Anthropic as the primary provider and OpenAI as the secondary. No
Anthropic API key is available for this project, and none is likely to be. The
baseline (M6) is built and unrun; no system has been scored, on any set, with any
model. So this decision is being made **before any measurement exists**, which is
the only point at which changing the model costs nothing.

## Decision

**The primary is OpenAI `gpt-5.5-2026-04-23`, for the baseline and for Receipts
alike.** The secondary is `none`.

### Same model on both sides

The thesis (PDD §5) compares a constrained architecture against a free-form
baseline *using the same model*. A cross-model comparison measures nothing: if
Receipts used Claude and the baseline used GPT, a difference in silent-wrong
rate would be a statement about two vendors, not about planning-versus-prompting.
So the switch is not "the baseline moves to OpenAI" — it is the project's single
model, changed once, before anything was scored.

### Why this model

Four candidates were tested live against the exact pattern M9 depends on — a
JSON schema generated per request from the semantic slice, with `name` an enum of
that slice's metrics, `dimensions` an enum of their allowed dimensions, nested
window objects, and an `anyOf` alternative for `{"no_fit": true, ...}`. All of
`gpt-5.5-2026-04-23`, `gpt-5.4-2026-03-05`, `gpt-5.6` and `gpt-5` produced
schema-valid plans, refused correctly on a question no allowed metric covers, and
refused correctly on a question whose tempting dimension (`salesperson`) is not
in the enum. None emitted a value outside an enum, which is the property that
makes "an unknown metric is unrepresentable" true rather than hopeful.

Given that they all passed, the choice came down to two constraints:

- **Strongest, as instructed.** `gpt-5.5` is the newest general model in the
  family with a dated snapshot.
- **Pinnable.** `gpt-5.6` is nominally newer and a quarter of the price, and it
  was rejected for one reason: it has no dated snapshot. The model list exposes
  `gpt-5.6-luna`, `-sol` and `-terra`, and the bare `gpt-5.6` is an alias. An
  alias can move. If it moved between the baseline's recording and Receipts'
  recording — weeks apart, by design — the thesis would be comparing two models
  and nothing in the pipeline would say so. A moving alias is not a cheaper
  option; it is a different experiment with the same name.

Runner-up: `gpt-5.4-2026-03-05`, dated, half the input price, and identical on
every smoke case. If cost becomes the binding constraint for the holdout runs, it
is the switch to make — and it must then be made for **both** arms, with the
baseline re-recorded.

### No secondary

`secondary: {provider: none, model: none}` — the M5 cut-line. A fallback to a
different model would violate "same model on both sides" precisely when nobody is
watching: a transient 529 on one trial, a quiet answer from another model, and a
row in the results that means something different from its neighbours. Raising
`ModelUnavailable` and re-running the trial is the honest failure.

## Consequences

**Temperature is no longer 0.** SDD §16 says temperature 0 everywhere. The gpt-5
family accepts only its default and returns `400 Unsupported value:
'temperature' does not support 0 with this model`. The parameter is therefore
omitted, and `config/settings.yaml` records `temperature: null` rather than a 0
that is not true.

Run-to-run reproducibility no longer comes from the sampler. It comes from
record/replay (SDD §16): a recorded run replays byte-identically, which is what
D16 actually requires, and the recording is the artifact the thesis publishes.
What is lost is the ability to re-record and get the same bytes, which was never
guaranteed across model versions anyway. Recorded in LIMITATIONS.

**Prices change.** `config/pricing.yaml` now carries `gpt-5.5-2026-04-23` at
$5.00 / $0.50 cached / $30.00 per Mtok, read from OpenAI's published pricing on
2026-09-12, and gains a cached-input rate for every model.

**Anthropic is not deleted.** `receipts/llm/anthropic.py` stays, tested, unused.
The cost of keeping it is nil and it is the thing that makes this decision
reversible.
