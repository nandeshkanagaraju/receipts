# M1 — holdout batch 2, and your six rulings applied

Batch 2 is unchanged in membership: HO-028…HO-054, ANS 16 · AMB 3 · UNA 3 ·
DENY 3 · LIVE 2. This revision applies all six rulings, rewrites three questions,
and turns the two things that were only remembered — the self-check and the
rule-7 audit — into a documented list and a freeze gate.

---

## 1. Files created/changed

| File | What |
|---|---|
| `eval/questions/README.md` | authoring **rule 11** (filter swaps) · the **self-check, items 1–9** · the two new freeze gates |
| `scripts/skeleton_audit.py` | moved from `_review/`, rewritten as a module with an importable `collisions()` |
| `scripts/freeze_questions.py` | gate 4 (**zero collisions**) · `document_digests()` / `check_documents()` · records `question_documents` |
| `tests/injection/test_freeze_questions_gate.py` | 12 → **23** tests: injection + meta for both new guards |
| `docs/GLOSSARY.md` | §6.1 stale row replaced by two rows matching §1.9 and §5.3a |
| `docs/M2_NOTES.md` | M4 note — a reference value of 0 is compared **exactly** |
| `eval/questions/eval.jsonl` | **EV-073** rewritten · **EV-076** reshaped |
| `eval/questions/holdout.jsonl` | **HO-032** snapshot moved off A3's window |
| `eval/questions/_review/holdout_batch02.md` | re-rendered against the edited questions |
| `eval/questions/_review/selfchecks.json` | HO-032's entry updated |
| `_reports/M1-holdout-batch02.md` · `_reports/URLS.md` | this file, and the link list |

No new dependencies. `docs/PDD.md`, `docs/SDD.md`, `kestrel_gen/` and
`config/thresholds.yaml` untouched.

## 2. Tests

**85 passed, 1.05s** (was 74). **11 new**, all in the freeze-gate injection file,
which goes from 12 test functions to 23:

| Guard | Injection | Meta | Also |
|---|---|---|---|
| rule 7 collisions | a planted question that is another with place and window swapped → refused, **naming both qids** | with `enabled=False` the same corpus passes, and `all_gates(check_collisions=False)` reports nothing | a precondition (3 distinct questions → 0), a false-positive guard (month vs rolling-7-days → 0), and the real 264 |
| question documents | one character flipped in a **copy** of GLOSSARY.md → detected | with nothing recorded, the same edited copy passes | absence after the tag is itself a failure; the real manifest is consistent in whatever state it is in |

`docs/` is never edited by a test: both document tests copy the files into
`tmp_path` first, the same pattern `tests/charter/test_freeze.py` already uses.

## 3. VERIFY output

```
make test          85 passed in 1.05s
make lint          All checks passed! · 110 files already formatted
make types         Success: no issues found in 77 source files
make freeze-check  freeze-check passed

python scripts/skeleton_audit.py                     (exit 0)
264 questions, 264 distinct skeletons, 0 colliding group(s)

python scripts/freeze_questions.py --check           (exit 1)
REFUSING to create the questions-frozen tag. 1 problem(s):
  holdout_blind.jsonl is missing. ...
trap coverage across all sets:
  attempts_vs_orders        20  ok      test_transactions          7  ok
  authorised_vs_captured     7  ok      emi                       12  ok
  capture_vs_settlement     19  ok      duplicate_captures         6  ok
  fiscal_calendar           15  ok      local_time                 9  ok
  multi_currency             9  ok      partial_refunds           25  ok
```

Still one blocker, still the blind file. Selected test output:

```
precondition: 3 distinct questions -> 0 problem(s)
injection: planted a filter swap -> 1 problem(s)
  filter-swap collision: XX-001, XX-004 share the skeleton
  'net revenue <COUNTRY> <MONTH> <CUR>' [ANS/scalar]
meta (collision gate off): 0 problem(s) — expected 0
month vs rolling-7-days -> 0 problem(s) — expected 0
real corpus: 264 questions, 0 colliding group(s)

  docs/GLOSSARY.md  9ded46304caeadab6cae8b1546fc84f28feaa7459704f363a83faf1b16616f41
  docs/M2_NOTES.md  a6840c3b2d6e64f9cc56802fe0b0886ee1723ac7d5b8816b712a5fd9b9ec4c35
injection: one character in GLOSSARY.md -> 1 mismatch(es)
  docs/GLOSSARY.md: manifest 9ded46304caeadab… != actual c46f6e529422a0e0…
meta (no question_documents recorded): 0 problem(s) — expected 0
tagged but unrecorded -> 1 problem(s)
  specs-frozen exists but the manifest records no question_documents;
  the glossary the answers were written from is unpinned
real manifest question_documents: not yet recorded (questions-frozen does not exist)
```

The two document hashes above are today's. They are **not** written to
`FREEZE_MANIFEST.json` yet — `freeze_questions.py` records them when it creates
the tag, which is the point at which they stop being allowed to move.

## 4. Ruling 1 — the self-check and the audit are enforced, not remembered

**The self-check now lives in `eval/questions/README.md`**, as a table of items
1–9 with the authoring rule each one enforces. It was previously reconstructable
only from the roll-up tables inside the batch files, which is how it came to be
applied slightly differently in different batches.

Two notes on the move:

- **The README already carried authoring rules, and there are twelve of them
  now, not ten.** Your ruling said "authoring rules 1–10"; the file has had 11
  since the small-denominator rule landed in batch 1. I left all eleven in place
  and added a twelfth — see below — rather than renumbering, because the batch
  files already cite "rule 10" meaning small denominators.
- **The new rule 11 is "a filter swap alone is not a difference."** It was the
  one authoring rule that existed only in prose in the batch reports, which is
  exactly why it went unenforced long enough for two pairs to slip through. It is
  now a written rule with a gate behind it.

**`scripts/skeleton_audit.py`** is out of `_review/` (which is deleted at
`questions-frozen`) and into `scripts/`, where it survives. It exposes
`collisions()`, and `freeze_questions.gate_collisions()` calls it as **gate 4**:
the tag is refused while any two questions collide, with the refusal naming both
qids and the shared skeleton.

## 5. Ruling 2 — the stale row, every "final attempt" hit, and the hashes

### Every hit for "final attempt" in the repository

```
docs/GLOSSARY.md:195  **Why not attribute the order to its final attempt.** It inverts the metric.
docs/GLOSSARY.md:196  Under final-attempt attribution the order above leaves UPI's denominator
docs/GLOSSARY.md:471  denominators overlap. §1.9 explains why final-attempt attribution would make a
docs/GLOSSARY.md:890  | per-bank / per-method order breakdowns | Attributed to the final attempt | §1.9 |
```

Four hits, in one file. **Three are correct and stay**: 195–196 are §1.9's
argument for why final-attempt attribution is wrong, and 471 is §2.8 citing that
argument. Only **890** asserted it as Kestrel's rule. Nothing outside
`docs/GLOSSARY.md` mentions it — no question, no test, no source file. The grep
covered `docs/`, `eval/`, `tests/`, `src/` and `scripts/`, for "final attempt",
"final-attempt", "last attempt" and "latest attempt".

### The fix

The §6.1 row is replaced by two, because the single row was collapsing two rules
that §1.9 and §5.3a deliberately separate:

| Term | Default | Section |
|---|---|---|
| per-method / per-bank **success rates** | **"Tried" attribution** — the order sits in the denominator of every method, bank and network it attempted, and in the numerator of the one that captured. Per-method rates therefore do not sum to the overall rate | §1.9, §2.8 |
| "EMI orders", "card-paid orders", and per-method **value** splits | The **paying** method — the attempt that captured. An order that tried UPI and paid by card is a card order | §5.3a, §1.9 |

No question changes as a result: every per-method question in all three sets was
already written to §1.9 and §5.3a, which is why the stale row never produced a
wrong question. It would have produced a wrong *implementation*, since M7 builds
the semantic layer from this document.

### The hashes

`freeze_questions.py` now hashes `docs/GLOSSARY.md` and `docs/M2_NOTES.md` into a
`question_documents` section at freeze time, and `check_documents()` verifies
them. The asymmetry is deliberate and is the part worth reviewing:

- **Before the tag**, an unrecorded section is legitimate — the documents are
  still being written, which is the licence you just granted.
- **After the tag**, an unrecorded section is *itself* the failure. A
  `questions-frozen` repo whose glossary is unpinned means the reference SQL was
  written from a document that can still move.

That keeps it a real assertion rather than a conditional one: the condition is
the existence of the tag, which is an observable fact, not the convenience of the
moment.

## 6. Ruling 3 — both collisions fixed, audit clean

| qid | Was | Now | Why this shape |
|---|---|---|---|
| **EV-076** | Net revenue in the UK in July, in pounds. | **Net revenue for pay-later orders in the UK in July, in pounds.** | Keeps its purpose exactly — single-currency money, no FX join expected, `partial_refunds`, `global_finance`, GBP. The shape changes from a bare country total to a method-qualified one, which also exercises §5.3a's paying-method rule |
| **EV-073** | Payment failure rate by reason in the UK in July. | **What share of our UK payment attempts succeeded in July?** | Failure-rate-by-reason is already carried three times (DV-009, EV-019, EV-130), so dropping this instance costs nothing. **Attempt-level success rate (§2.9) appeared nowhere in `eval.jsonl`** — only once in dev, DV-028 — so the rewrite fills a real gap. `table`/top_k 5 → `scalar`; trap `null` → `attempts_vs_orders` |

```
264 questions, 264 distinct skeletons, 0 colliding group(s)
```

Corpus-wide `attempts_vs_orders` goes 19 → 20 as a result; every other trap count
is unchanged.

## 7. Ruling 4 — HO-032 moved, and every other overlap

**HO-032's snapshot moved from `2026-09-06` to `2026-07-31`.** The old date was
A3's window *and* DV-059's subject, so the top of the by-bank ranking would have
been the planted bank. July is clear of all six planted windows. It stays
distinct from EV-055 by dimension, and the audit agrees.

### The rest of the holdout, checked

I resolved every holdout window against `as_of` and intersected it with each
anomaly's window, then filtered by whether the anomaly's **place** is in scope
and its **metric family** is the one asked for. Window overlap alone is not a
finding: five of six anomalies sit in August 2026, and August is "last month" —
the most natural window in a set whose reporting date is 10 September. What
matters is whether the anomaly moves the number.

Of the **35** holdout questions with a computed answer (ANS 32 + LIVE 3):

| | Count | Which |
|---|---|---|
| Window clear of all six anomalies | **10** | HO-005, HO-007, HO-011, HO-013, HO-027, HO-029, **HO-032**, HO-035, HO-053, HO-054 |
| Window overlaps, but no anomaly touches the place *and* the metric | **10** | HO-002, HO-004, HO-009, HO-012, HO-028, HO-031, HO-039, HO-041, HO-042, HO-043 |
| Background — the anomaly moves the level uniformly, so rankings hold | **4** | HO-006, HO-014, HO-030, HO-038 |
| **Materially shaped** | **11** | the table below |

**The eleven, ranked:**

| qid | Anomaly | What it does to the answer |
|---|---|---|
| **HO-037** | A6 | **Dominant.** "Refunds on orders captured twice in Tamil Nadu last month" *is* A6. Without the planted duplicates the answer is near zero |
| **HO-033** | A5 | Strong. A UK card decline in August is precisely what makes a customer switch method, which is what this counts |
| **HO-015** | A5 | Strong. Declines produce retries, and this is attempts per paid order in the UK in August |
| **HO-010** | A5 | Strong, and it is EV-148's subject read as a level rather than a "why" — the UK capture rate in August is what A5 moves |
| **HO-040**, **HO-034** | A6 | The TN refunds A6 creates land in both the full/partial split and the by-method refund rate |
| **HO-036** | A4 | The August point of the Singapore series is the launch surge |
| **HO-016**, **HO-001** | A4, A5 | One or two country columns carry the anomaly; the other four are ordinary |
| **HO-008** | A1 | Four of its seven days sit inside A1's window, depressing TN captures |
| **HO-003** | A6 | Only if A6's duplicated orders happen to be Kestrel Onyx — unknown until the generator runs |

**A7 is everywhere by construction** — test rows in the production tables — and
every `test_transactions` question depends on that. It is not an overlap to
remove; it is the trap.

### What I recommend, and what I have not done

Your ruling asked for **no** holdout answer shaped by a known planted anomaly.
Read strictly that is unachievable: it would mean no holdout question may use
"last month", which removes the most common window in the corpus and makes the
holdout unrepresentative of dev and eval — a different and worse distortion.

So I moved the one case where the question's answer *is* the anomaly's answer
(HO-032) and I am flagging **HO-037** as the remaining one of that kind. It is a
deliberate choice — I picked it partly *because* A6 guarantees a non-zero
answer — and it is your call:

- **Keep it.** The reference SQL computes what is there; a system that gets it
  right has done real work, joining duplicates to refunds.
- **Or move it to July**, where the answer is whatever ordinary duplicate rate
  the generator produces — possibly zero, which makes it a weak question.

I have not changed it.

## 8. Ruling 5 — a zero reference compares exactly

Added to `docs/M2_NOTES.md` §5 as an M4 note, ahead of the tie rule. In short:
`tolerance_rel` is undefined against zero, and a zero reference is a claim that
the quantity does not exist rather than a rounding target, so "close to zero" is
wrong in both directions. Two consequences recorded with it: **M3** must return a
row containing 0 rather than zero rows, since the scorer cannot distinguish an
empty result from a zero one afterwards; and the rule applies to a zero **cell**
inside a table answer, not only to a scalar.

It names HO-043 as the case, on your instruction. That is the only holdout
question named in `M2_NOTES.md`, and the note says so — it gives the qid and the
scoring rule, not the question.

## 9. Ruling 6 — the six flagged items, with proposed resolutions

| # | Flag | Proposed resolution |
|---|---|---|
| 1 | DV-050/EV-076 and EV-019/EV-073 collide as filter swaps | **Done under ruling 3.** EV-076 reshaped, EV-073 rewritten, audit clean at 264. No further action |
| 2 | HO-032 sits on A3's window and dimension | **Done under ruling 4.** Snapshot moved to 2026-07-31. **HO-037 is the remaining case of the same kind** — §7 sets out keep-or-move; my recommendation is **keep**, because the join it requires is real work and a July version risks a zero answer |
| 3 | HO-043's correct answer is zero | **Partly done under ruling 5** — the scoring rule is recorded. The open half is M3: the reference SQL must return a row containing 0. I propose **keeping the question** and adding it to M3's checklist, because it is the only test of GLOSSARY §2.11's "legitimately zero rather than missing" |
| 4 | HO-043 and EV-142 are the same sentence with different outcomes | **Keep both, unchanged.** The pair separates a scope refusal from a structural zero, which a weak system conflates by answering "no EMI here" to both. The audit distinguishes them by place grain and population, so it is not a rule-11 case. No action proposed |
| 5 | HO-046 is the closest rule-7 call in the batch | **Keep, and record why.** It survives on two axes of ambiguity against EV-085's one (entity + measure vs measure), and DV-052 covers entity alone. If you disagree, the replacement I would write is an AMB with a **measure** ambiguity over accessories in Tamil Nadu, which keeps the population and role and drops the Anna Nagar reuse entirely |
| 6 | HO-052 is the sixth adversarial deny; 5 of 16 denies are now adversarial | **Keep, and accept the proportion.** Its vector — an asserted prior scope change, the D14 case — is the only one in the corpus that is not an instruction override. Eval runs 3 adversarial in 10 denies and the holdout 2 in 6, which is close. The alternative, rewriting it as a plain cross-region deny, duplicates HO-024 in shape |

## 10. Deviations from the SDD

**None.** Two choices worth stating, neither a deviation:

1. **The README now has twelve authoring rules, not ten.** Explained in §4; I did
   not renumber, because the existing batch files cite "rule 10".
2. **`question_documents` is a new manifest section**, owned by
   `freeze_questions.py`, parallel to `documents` (owned by `freeze.py`, the G0
   specs). Keeping them separate preserves `freeze.py --check`'s meaning: the
   specs are frozen *now*, the question documents are frozen *at the questions
   tag*. Merging them would have made `make freeze-check` fail on every glossary
   edit between now and then — the licence you just granted, revoked by an
   implementation detail.

## 11. Unsure about

- **HO-037** — the one remaining question whose answer is a planted anomaly.
  §7 and §9 set out the options; I have not moved it.
- **The audit's masker is a word list.** It knows the place names, window
  phrasings and currencies this corpus uses. A question written with a phrasing
  it does not know — a new city, "the past fortnight" — is invisible to it, and
  the gate would pass a filter swap expressed that way. The module docstring says
  so. Two mitigations exist and neither is free: assert against a closed
  vocabulary drawn from `M2_NOTES` §1.3 (breaks when the world grows), or parse
  properly (needs a real grammar). I would leave it and rely on item 7 also being
  done by hand, which is what the README now says.
- **Nothing yet writes `question_documents`**, because nothing has run
  `freeze_questions.py` without `--check`. The first real freeze will. Until
  then `check_documents()` correctly reports zero problems against a manifest
  that records nothing, and the test that proves the *tagged* case uses
  `specs-frozen` as a stand-in tag that does exist.
- **Two files I updated were silently reverted by a branch switch** while I was
  working: `_reports/` and `eval/questions/_review/` are tracked on this branch
  and gitignored on `main`, so checking out `main` deletes them and checking this
  branch out again restores the *committed* version over the working copy. I
  rebuilt both. It is the same mechanism that made PR #2 red, and it is worth
  knowing before you edit either directory by hand.
- **Translations remain the other open item** — 264 English variants written,
  `ta`, `hi` and `ta-Latn` empty with provenance `pending` across all three sets.
