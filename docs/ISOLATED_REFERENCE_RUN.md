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

## 1a. The world this brief describes

The generator was reopened once after this brief was written, for one
conformance defect (**ADR-014**): `payment_attempts.status` had no `authorized`
rows though SDD §5.2 declares the status. Roughly 2% of card attempts now end
`authorized` — funds reserved, hold expired or voided, never captured.

    generator     gen-frozen-2          (gen-frozen is NOT moved)
    data_version  1c253c54cd598c861e800f5bf34b8c5f5c2a4ea294b3a4444671db7848344f4b

**Check `data/MANIFEST.json` reads that `data_version` before writing a single
query.** If it does not, the worktree is on an older world, and every reference
written against it will be wrong in a way that looks like a disagreement later.
Regenerate with `make data`.

What this means for the holdout references:

- **`status = 'captured'` is now materially different from `status <> 'failed'`.**
  Write the first. The second silently counts expired authorisation holds as
  money, which is the §4.2 trap, and six dev/eval questions now detect it.
- An `authorized` attempt carries **no `failure_reason`**, so it belongs in no
  failure-reason breakdown (§2.10).
- Captured GMV, refunds, settlements and every planted anomaly are byte
  identical to the world before the fix, and `eval/sealed/` hashes to exactly
  what it hashed to at `gen-frozen`. Only the status and failure reason of the
  converted rows changed.

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
`eval/reference_sql/HO-*` and `eval/questions/holdout*`. The lift is built; do
not improvise one.

```
cd ../receipts-isolated
make setup                                            # its own .venv; the worktree has none
touch .isolated-run                                   # lifts the hook's holdout half
cp .claude/settings.isolated.json .claude/settings.json
git update-index --assume-unchanged .claude/settings.json
```

`.isolated-run` is gitignored. `settings.isolated.json` is `main`'s deny list
with exactly the holdout entries removed — every `.env` and `eval/sealed` entry
is intact, and the marker does not lift those either, with or without it.
`--assume-unchanged` is what stops the relaxed settings being staged;
`test_isolated_lift_does_not_travel` is what fails if they reach `main` anyway.

**This worktree has no world.** `data/` (254M) and `truth/` are gitignored and
per-tree, so the new worktree starts without them. Copy them across rather than
regenerating:

```
cp -R data truth ../receipts-isolated/
```

The copy needs no seed, and the seed stays in one tree. Then, before writing a
single query, assert the world is the one this brief describes:

```
python -c "import json;print(json.load(open('data/MANIFEST.json'))['data_version'][:8])"
```

It must print `1c253c54`. If it does not, stop: the reference SQL would be
written against a different world from the one the answers were measured in.

Regenerating in the worktree (`make data`) is the fallback and it **reads
`.env`**, which is the one thing this arrangement is trying to keep in a single
place. Prefer the copy.

---

## 3. Inputs

### May read

| Path | Why |
|---|---|
| `eval/questions/holdout.jsonl` | the questions. This is the point. |
| `~/receipts-blind/human_questions.txt` | the blind 30 as **raw human text**, outside the repo (§7) |
| `eval/questions/holdout_blind*.jsonl` | only if a previous run already wrote it |
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
     current **and** the comparison value, keyed `current`/`comparison`.
   - `expected.kind` and the shape flags must agree: `scalar` never carries
     `top_k`, `series` or `compare`, and `series` never carries `top_k`. Eleven
     dev/eval rows broke that and were corrected;
     `tests/unit/test_question_consistency.py` now enforces it over the holdout
     too, reporting a count and never a qid.
   - **Do not put the question text in the `.sql` header.** The dev and eval
     files carry it for the reviewer; an `HO-*.sql` file is tracked in git, and a
     header restating the question turns an accidental read into a full leak
     rather than a partial one. Name the metric and the glossary sections, not
     the sentence.

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

### 4a. If a holdout scan fails, you are the only one who can fix it

`test_holdout_questions_stay_inside_their_role_scope`,
`test_holdout_kind_and_shape_flags_agree` and
`test_no_holdout_question_breaks_authorisation_down` report a count and refuse to
say which rows. That is deliberate, and it means the main session cannot act on
them: **this session is the only context that can see the offending rows at all.**

Fix by changing `role`, or `expected.kind` and the shape flags. **Never the
question text.** The text is hashed in three languages in
`docs/FREEZE_MANIFEST.json`, `translations-frozen` is pending on those hashes,
and a reworded holdout question is a different question with the same qid.

If a row cannot be fixed without changing its text, leave it, flag it in §5.3 and
report the count. That is a ruling for the person who launched the session, not a
decision for this one.

Report a count in the hand-back: how many rows each scan flagged, and how many
were fixed. Not which.

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

The `blind_*` counts are separate from the holdout ones because they answer a
different question: the holdout counts say the work is complete, the blind counts
say what the human actually wrote. They are the realised mix of §7, not the
forecast — fill them from the file, and if they do not match ANS 22 · AMB 5 ·
UNA 3, that is the finding rather than something to correct.

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
    "flagged_implausible": 0,
    "blind_questions_read": null,        <-- the realised count, filled from the file
    "blind_classified_ans": 0,
    "blind_classified_amb": 0,
    "blind_classified_una": 0,
    "blind_sql_files": 0,
    "blind_authored_by": "human-blind"
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

`_reports/isolated-reference-run.md` (`_reports/` is gitignored; per HANDOFF §4.7
reports go to a secret gist). It may hold counts, per-qid booleans, timings, and
the flags from §4, item 6. It goes to the person who launched the session. **The main
session never reads it.**

### 5.4 The counts-only marker, if this ever runs in CI

One line, the format `_ci/sealed_gate.txt` already established:

```
holdout reference: 35 of 35 pass
```

Written by the job that has the evidence, read by the job that needs the
verdict. `N of N`, nothing else. A guard that cannot run in an environment must
fail there, not go quiet (HANDOFF §4.9).

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

**No holdout text in a gist. Ever.** A secret gist is not a private one: it is an
unlisted URL, readable by anyone who has it, forwarded as easily as any other
link, and outside the deny rules and the hook entirely — those guard this
repository, and a gist is not in it.

This rule is written here because it was broken. A ta-Latn worksheet carrying
fifteen holdout questions in English and Tamil was published as a secret gist,
and an audit of the account then found five older gists carrying holdout qids —
two of them with question-shaped text on the same line. Reports go in gists;
holdout content does not, which means a report that would need holdout content is
a report that gets written as counts instead.

Where holdout text has to be written down for a human, it goes **outside the
repository** — `~/receipts-blind/` — and is deleted when it has been used.

**Assertions are the trap.** `assert got == expected, f"expected {expected}"`
puts the answer in the terminal precisely when someone is watching. Print
pass/fail and counts; never a value. `tests/charter/test_sealed_values_never_printed.py`
already enforces this shape for `eval/sealed/` and is the pattern to copy.

Permitted at the boundary, and sufficient: counts, per-qid booleans, SHA-256
hashes, pass/fail verdicts, wall-clock timings, and a bare list of flagged qids.

---

## 7. The blind 30

The blind questions arrive as **raw human text** at
`~/receipts-blind/human_questions.txt` — outside the repository, one question per
line, unclassified. `eval/questions/holdout_blind.jsonl` does not exist yet:
**writing it is this session's job, not its input.**

That means: converting each line to the format of SDD §25.1, classifying it into
a population, translating it, and writing `HO-B*.sql` for the ANS ones.
`authored_by` is `"human-blind"` — distinct from `"model-blind"`, which is the
fallback label for questions a model wrote when no human file arrived (HANDOFF
§3.2, deadline 2026-09-13 20:00). The two labels must never be mixed: which
questions a human actually wrote is the entire value of the set.

**The file holds 32 questions, not 30.** Realised after the run, and recorded
here so the next reader does not re-derive it: the source is `ROLE|question`
records hard-wrapped at 72 columns, so an earlier count of 29 counted *lines*,
not questions. No line was discarded. **Write exactly what the file contains: never pad to 30, never reword,
never split one line into two to reach a count.** A blind set bent into a target
is no longer blind, and the bend is invisible once made.

Some lines may not be questions at all — a heading, a note to self, a blank. Skip
them and **report how many were discarded and why** ("two headings", "one line
was a note about the format"). Never quote a discarded line: it came from the
same head as the questions, and the reasons are all the main session needs.

**ANS 22 · AMB 5 · UNA 3 is a forecast, not a quota.** Classify what the human
actually wrote and report the realised mix, whatever it is. If it comes out
ANS 26 · AMB 2 · UNA 1, that is the finding and it goes in the hand-back.

`HOLDOUT_BLIND_TARGET` and the three other places carrying 30 are **not** yours
to change. They are reconciled on `main` after the hand-back, from the realised
count. Changing them here would mean the count was chosen by the session that
also chose the questions.

### The blind arm runs the same four gates

All four corpus scans run over the blind arm, inside this session, because this
session is the only one that can see the rows:

- role scope (`test_holdout_questions_stay_inside_their_role_scope`)
- kind/shape agreement (`test_holdout_kind_and_shape_flags_agree`)
- authorisation breakdowns (`test_no_holdout_question_breaks_authorisation_down`)
- every ANS/LIVE qid has a reference file and every file a qid (§4, item 5)

Fix by `role`, `expected.kind` or the shape flags — **never the question text**,
for the same reason as §4a and with more force here: the text is the human's.
Report counts: how many each scan flagged, how many were fixed. Not which.

### Translations for the blind arm

Write `ta` and `hi`, labelled `machine_unverified` like every other machine
draft. **`ta-Latn` stays `pending` for the blind arm permanently.**

The reason is structural, not a shortage of effort: the reviewer writes the
Tanglish by hand for the rest of the corpus, and hand-writing it for these 32
would mean reading them — which unblinds the one person the blind set exists to
keep out. M14 reports the blind arm in **en/ta/hi only**, and `LIMITATIONS.md`
records the asymmetry.

The main session sees counts only. It does not classify them, does not review
them, and does not learn what they ask.

---

## 8. Hand-back

A single message to the person who launched the session, containing:

- the branch and commit SHA;
- the `counts` block from §5.2, verbatim;
- the flagged qids from §4, item 6, as a bare list;
- wall-clock time;
- confirmation that §6 was not violated;
- a pointer to `docs/adr/017-holdout-boundary-guards.md`, which is the record of
  what the boundary does and does not guarantee. The G5 report points at the same
  ADR. A reader asking whether this holdout was really blind should find one
  answer, written once, including the parts that are advisory.

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
  who launched the session has ruled on it;
- **the branch's committed `.claude/settings.json` is byte-identical to main's.**
  Check it, do not assume it:

  ```
  git diff main -- .claude/settings.json     # must print nothing
  ```

  `--assume-unchanged` stops an accidental `git add`; it does not stop a
  deliberate one, and this is the failure that unblinds every future session
  with nothing in a later diff to show it.

  A clean `git diff` is not enough on its own: with `--assume-unchanged` set, git
  is *told* not to look, so the diff is empty whether the file matches main or
  not. Check the flag is actually set, and check the file against main with the
  flag out of the way:

  ```
  git ls-files -v .claude/settings.json     # must start with a lowercase h
  git diff main -- .claude/settings.json    # must print nothing
  ```

  Lowercase `h` means assume-unchanged is in force. If it prints `H`, the flag
  was never set and everything above was a coincidence.

`questions-frozen` waits for this run *and* for the blind set (§7). Freezing
with an incomplete reference set would record a manifest that does not describe
the holdout, and the tag is the thing that makes the manifest worth having.
