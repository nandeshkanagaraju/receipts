# The isolated reference run

**Status:** the brief for a session that has not been launched yet.
**Written:** 2026-09-11, during M3, by the main build session — which is the one
thing this document exists to keep away from the holdout.

---

## 1. Why this session exists

M3 writes `eval/reference_sql/<qid>.sql` for every ANS and LIVE question in dev,
eval and holdout. For dev and eval that is ordinary work and the main session
does it. For the holdout it cannot, and the reason is worth stating precisely
rather than as a slogan.

A reference query restates its question in a form *more* exact than the English:
the numerator, the denominator, the date key, the window boundaries, the scope
predicate, the currency conversion, the exclusions. To write 35 of them is to
learn what the holdout asks about — which metrics, which grains, which traps,
which corners of the schema. The author then writes `semantic/*.yaml`, the
glossary synonym lists and the planner prompts. Nothing dishonest has to happen
for the holdout to stop measuring what it claims to measure; the ordinary drift
of building toward what you remember needing is enough, and it is invisible
afterwards because there is no artifact recording it.

So the reading and the building are put in different sessions, and the boundary
between them carries counts, hashes and verdicts — never content.

**This is weaker than a second person, and the weakness is the honest part.**
The same author launches this session and could read its transcript. What the
arrangement buys is that the build context provably never held the questions,
and that reading them is a deliberate act leaving a trace. That is the most a
repository can claim, and `LIMITATIONS.md` says so in those words.

---

## 2. Where to run

A **separate git worktree** and a **separate session**. Not a second tab on the
same checkout: `docs/M2_NOTES.md` §5 records what two writers in one tree cost
last time, and the standing rule from that incident — one writing session per
working tree — is not suspended for this.

```
git worktree add ../receipts-isolated -b isolated-reference main
```

The main session keeps `/Users/nandeshjeya/Documents/Receipts`. It does not
`cd` into the worktree, and it does not read files from it.

The block in `.claude/settings.json` and `.claude/hooks/deny_sealed_history.py`
is repository-wide and will be present in the worktree too. **The isolated
session is the one context permitted to lift it**, and only for
`eval/reference_sql/HO-*` and `eval/questions/holdout.jsonl`. Lift it by running
that session with its own settings — do not edit the committed
`.claude/settings.json`, because that file is the main session's control and a
change to it travels back on merge.

---

## 3. Inputs

### May read

| Path | Why |
|---|---|
| `eval/questions/holdout.jsonl` | the questions. This is the point. |
| `eval/questions/holdout_blind*.jsonl` | the blind 30, when they land (§7) |
| `docs/GLOSSARY.md` | every definition the SQL must follow literally |
| `docs/PDD.md`, `docs/SDD.md` | §6, §25.1, §25.3 |
| `docs/M2_NOTES.md` | §2a magnitude ranges, §4 population arithmetic, and the M3/M4 rulings in §5 |
| `docs/adr/009-question-format-extensions.md` | `interpretation`, `expected.compare`, `expected.series` |
| `eval/questions/README.md` | authoring rules, line format |
| `eval/reference_sql/DV-*.sql`, `EV-*.sql` | the main session's work, as worked examples of house style |
| `src/receipts/evalkit/reference.py` | the runner. Use it; do not fork it. |
| `scripts/double_compute.py` | the second calculation. Use it; do not fork it. |
| `data/`, `truth/anomalies.json`, `truth/constructed.json` | the world |

### Must not read

| Path | Why |
|---|---|
| `eval/sealed/**` | still sealed, for this session too. The holdout WHY questions are generated and carry no `reference_sql`; nothing in this job needs them. ADR-012 stands. |
| `.env` | the seed. Same rule as everywhere else. |

There is no exception here to negotiate. This session is isolated *from the
build*, not trusted *with everything*.

---

## 4. The job

1. **Write `eval/reference_sql/HO-<n>.sql`** for every ANS and LIVE question in
   `holdout.jsonl` — expected to be 35 files (ANS 32 · LIVE 3), but count them
   from the file rather than from this sentence. AMB, UNA and DENY questions
   carry no `reference_sql` and get no file.

2. **Follow the house rules**, which are not negotiable and are the same ones
   the dev and eval SQL follows:
   - `docs/GLOSSARY.md` literally. Where the row carries an `interpretation`
     sentence, that sentence governs: numerator, denominator, date key,
     currency, exclusions.
   - Output columns `key` (where the answer has one) and `value`.
   - An explicit `ORDER BY`, always (D4).
   - Money in the row's `expected.reporting_currency`, in **minor units**,
     converted by the glossary FX rule with `Decimal` arithmetic — never float
     (D1).
   - An `is_test` exclusion on every fact table touched.
   - `as_of` comes from the question row. No clock reads (D2).
   - A zero answer returns **a row containing 0, never zero rows**
     (`docs/M2_NOTES.md` §5). An empty result and a result of zero are different
     claims and the scorer cannot tell them apart afterwards. At least one
     holdout question depends on this.
   - Shape follows the flags: `top_k` → a ranking, ordered; `series: true` → one
     row per time key, no `top_k`; neither → a set. `compare: true` → return the
     current **and** the comparison value.

3. **LIVE questions** take their reference from `truth/constructed.json`
   (`refunds_pending_at_gateway`) joined in pandas, not SQL — SDD §6 and M3
   BUILD item 4.

4. **Double-compute all 35**, not a sample. The main session samples dev and
   eval; the holdout gets full coverage because nobody downstream will ever
   eyeball these values. Use `scripts/double_compute.py`, which computes in
   pandas straight off Parquet and shares no code with `reference.py` — a
   property an AST check enforces, so do not "helpfully" factor the two
   together.

5. **Run the four M3 tests over the holdout arm**: every ANS/LIVE qid has a file
   that runs and returns ≥ 1 row; the double computations agree within the row's
   `tolerance_rel`, exact where the reference is 0; the import isolation holds;
   an `is_test` exclusion is present in every file that touches a fact table,
   checked by walking the sqlglot AST and not by grepping text.

6. **Eyeball every value yourself.** Nobody else can. The main session's review
   round is the compensating control for dev and eval; for the holdout there is
   no second reader, so the first one has to be careful. Anything implausible is
   reported as a flag in §5, by qid, with no value attached.

---

## 5. Outputs

Three, and nothing else.

### 5.1 The SQL — tracked, unreadable from the build session

`eval/reference_sql/HO-*.sql`, committed. They are tracked in git exactly as
`eval/questions/holdout.jsonl` already is; the deny rules and the hook stop the
*build* session from opening them.

### 5.2 `eval/reference_sql/HO_MANIFEST.json` — tracked, machine-readable, safe

The only output the main session and the freeze gates read. Sorted keys, no
timestamps, no values, no SQL.

```json
{
  "generated_by": "isolated-reference-run",
  "counts": {
    "questions_ans_live": 35,
    "sql_files": 35,
    "run_ok": 35,
    "returned_at_least_one_row": 35,
    "double_computed": 35,
    "agree": 35,
    "flagged_implausible": 0
  },
  "files": {
    "HO-002.sql": {
      "sha256": "…",
      "runs": true,
      "returns_rows": true,
      "double_computed": true,
      "agrees": true
    }
  }
}
```

Per-file entries carry a hash and four booleans. **No row counts, no values, no
question text, no SQL fragment, no metric or dimension name.** A row count is a
small leak — it separates a scalar from a table from a series — and it buys
nothing the booleans do not, so it is not in the tracked file. It may appear in
§5.3, which is not committed.

At `questions-frozen` these hashes go into `docs/FREEZE_MANIFEST.json`, which is
what lets G5 prove the holdout was scored against the files that were frozen.

### 5.3 The report — for the human, not committed

`_reports/isolated-reference-run.md` (`_reports/` is gitignored; per HANDOFF §4.6
reports go to a secret gist). It may hold counts, per-qid booleans, timings, and
the flags from §4.6. It goes to the person who launched the session. **The main
session never reads it.**

### 5.4 The counts-only marker, if this ever runs in CI

One line, the format `_ci/sealed_gate.txt` already established:

```
holdout reference: 35 of 35 pass
```

Written by the job that has the evidence, read by the job that needs the
verdict. `N of N`, nothing else. A guard that cannot run in an environment must
fail there, not go quiet (HANDOFF §4.8).

---

## 6. What must never be printed

Anywhere: terminal, commit message, test output, CI log, the report, the
manifest, the hand-back message.

- Any holdout question, in any language variant, in whole or in part.
- Any reference SQL, in whole or in part — including a single `WHERE` clause.
- Any reference **value**, scalar or cell, rounded or exact, in any currency.
- Any metric name, dimension name, date window, country, showroom, model, bank
  or network **attached to a qid**. "HO-014 uses refund rate" is a leak; "33 of
  35 questions are scalar" is not.
- Any diff that would show the above. `git show`, `git diff`, `git log -p` over
  `eval/reference_sql/HO-*` belong to this session only, and their output does
  not leave it.

**Assertions are the trap.** `assert got == expected, f"expected {expected}"`
puts the answer in the terminal precisely when someone is watching. Print
pass/fail and counts; never a value. `tests/charter/test_sealed_values_never_printed.py`
already enforces this shape for `eval/sealed/` and is the pattern to copy.

Permitted at the boundary, and sufficient: counts, per-qid booleans, SHA-256
hashes, pass/fail verdicts, wall-clock timings, and a bare list of flagged qids.

---

## 7. The blind 30

When `holdout_blind.jsonl` lands (HANDOFF §3.2; deadline 2026-09-13 20:00, with
a documented fallback to `authored_by: "model-blind"`), **this session does all
of it**: converting the file to the line format of SDD §25.1, classifying each
question into a population, and writing `HO-B*.sql` for the ANS ones — expected
22, again counted from the file.

The main session sees counts only. It does not classify them, does not review
them, and does not learn what they ask.

---

## 8. Hand-back

A single message to the person who launched the session, containing:

- the branch and commit SHA;
- the `counts` block from §5.2, verbatim;
- the flagged qids from §4.6, as a bare list;
- wall-clock time;
- confirmation that §6 was not violated.

Then the worktree is merged (or the branch pushed) and removed. The main session
picks up `HO_MANIFEST.json` from `main` and nothing else.

---

## 9. Acceptance

This run is done when all of the following hold, and `HO_MANIFEST.json` shows it:

- `sql_files == questions_ans_live`, and both counted from `holdout.jsonl`
  rather than from this document;
- `run_ok == returned_at_least_one_row == sql_files`;
- `double_computed == agree == sql_files`;
- every file has an `is_test` exclusion where it touches a fact table, by AST;
- `flagged_implausible` is 0, or each flag is explained in §5.3 and the person
  who launched the session has ruled on it.

`questions-frozen` waits for this run *and* for the blind set (§7). Freezing
with an incomplete reference set would record a manifest that does not describe
the holdout, and the tag is the thing that makes the manifest worth having.
