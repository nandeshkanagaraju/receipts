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

| Anomaly | What it is (PDD §7) | Must be planted within | Named by | Role |
|---|---|---|---|---|
| A1 | UPI success dip, one issuing bank, Tamil Nadu | `2026-08-31` … `2026-09-06` (last complete Mon–Sun week) | DV-019, EV-097 | rm_tamil_nadu |
| A2 | Refund spike on one model at two Dubai showrooms | `2026-08-01` … `2026-08-31` (last calendar month) | DV-058 | global_finance |
| A3 | Settlement delay, one acquiring bank's EMI transactions | `2026-08-31` … `2026-09-06` (last complete week) | DV-059 | global_finance |
| A5 | Card decline spike in the UK after an auth change | `2026-08-01` … `2026-08-31` (last calendar month) | DV-040 | store_ops_uk |
| A4 | Launch-week sales surge for one model in Singapore | `2026-08-01` … `2026-08-31` (last calendar month) | EV-046 | global_finance |
| A6 | Duplicate captures at one showroom, later refunded | `2026-08-01` … `2026-08-31`, at a **Tamil Nadu** showroom | DV-022, EV-047 | rm_tamil_nadu |

A6's region matters: DV-022 asks for duplicate captures in Tamil Nadu under the
`rm_tamil_nadu` role, which is scoped to `IN-TN`. Planted anywhere else, the
scoped answer is zero and the question is trivial.

**All six planted anomalies A1–A6 are now pinned by a frozen question.** A4 is
pinned by EV-046 and A6 gains a second question, EV-047, at the same window as
DV-022.

Three eval WHY questions deliberately ask about an anomaly at a **coarser scope**
than the dev question for the same anomaly, so the agent must locate the
dimension as well as confirm the change:

| Anomaly | Dev question | Eval question | Difference |
|---|---|---|---|
| A2 | DV-058 names the UAE | EV-048 names **no country** — "one of our phone models" | The agent must find the country *and* the model |
| A6 | DV-022 counts duplicates in TN | EV-047 asks why refunds rose at a TN showroom | Duplicate captures are the cause, not the asked-for metric |

### 1.1 Magnitude: anomalies must clear the why-agent's confirm gate

Naming the right window is not enough. `why()` (SDD §15 step 1) refuses to
proceed unless the change it is asked about is both:

- **≥ `why.min_rel_change`** — 2% relative change, and
- **|z| ≥ `why.min_z`** — 2.0 against the trailing `why.trailing_periods` (28)
  equivalent periods.

Both thresholds are evaluated **at the granularity the question asks about**, not
at the granularity the anomaly was planted at. An anomaly planted on a single day
can easily clear both at day level and fail both once diluted across the week or
month the question names — in which case the agent correctly returns "no
significant change" and the question scores as a miss.

So for each anomaly, the generator must **either** spread it across enough of the
named window **or** size it so the aggregate still clears both gates:

| Anomaly | Question granularity | Requirement |
|---|---|---|
| A1 | **Week** (DV-019 asks "last week") | Spread across several days of `2026-08-31`…`09-06`, or size the single-day dip so the whole-week UPI order-level success rate for Tamil Nadu moves ≥2% relative with \|z\| ≥ 2 against the prior 28 weeks |
| A5 | **Month** (DV-040 asks "last month") | Same test at month level for UK card failures across `2026-08-01`…`08-31`, against the prior 28 months — note the data only starts 2025-03, so fewer trailing periods are available and the z calculation must handle a short history explicitly rather than silently |
| A2 | **Month** (DV-058) | UAE refund rate for `2026-08` must clear both gates at country level |
| A3 | **Week** (DV-059) | Unsettled amount at the end of `2026-09-06` must clear both gates |
| A4 | **Month** (EV-046) | Singapore **captured GMV** for `2026-08` must clear both gates at **Singapore country** level against trailing months. A launch-week surge concentrated in one week must still move the whole month; if it cannot, widen the surge rather than inflating one week |
| A2 | **Month, city level** (EV-048) | Dubai **refund rate** for `2026-08` must clear both gates. See §1.2a: a global-level threshold is unachievable at any realistic size |
| A6 | **Month** (DV-022, EV-047) | DV-022 is an ANS count, so no z-gate applies there. EV-047 **is** a WHY and asks at **Tamil Nadu** level: TN **refunded amount** for `2026-08` must clear both gates against trailing months, **and the affected showroom must be the top contributor** when the agent decomposes by showroom. A move that clears the gate but leaves the planted showroom second scores as a miss |

### 1.1a0 A2 and A3: the level the question enters at

**A2 is pinned to two named showrooms**, `Kestrel Dubai Garden Road` and
`Kestrel Dubai Central 2`, rather than "the two busiest in Dubai". DV-058 and
EV-048 now name the first in the question text, so which showroom carries A2 must
be a fixed fact about the world rather than an outcome of the draw.

The rephrasing moves the questions' **entry level** to the showroom, which is the
only level where A2 can clear the confirm gate. The arithmetic: 76 qualifying
orders of the affected model against 310 processed refunds in Dubai that month,
so refunding every single one is +25% of the city — under two standard deviations
of a noisy monthly series. The agent must still find the **model**; only the
showroom is given.

**A3 spans two consecutive weeks**, `2026-08-24`…`2026-09-06`, and the affected
bank's settlements are pushed four days later. Delayed settlements from the first
week therefore land *inside* the second, where the lag is visibly longer.
DV-059 and EV-098 ask about "last week", which is the second week
(`2026-08-31`…`2026-09-06`) — so their windows are unchanged and now measurable.

The previous single-week plant was invisible: pushing `settled_on` forward moved
those settlements *out* of the week being asked about, so the week lost them
rather than showing a longer lag, and the measured change was −0.13%.

### 1.1a Anomalies must be concentrated, not smeared

A planted anomaly has to have **one** answer, or the question that asks about it
has none.

- **A1 must sit in a single issuing bank.** EV-097 asks "why did UPI success drop
  for one of our issuing banks last week" and enters the anomaly by naming the
  bank dimension rather than the city. If the dip is spread across several banks,
  no single bank is the top contributor and the question stops being well posed.
  One bank, in Tamil Nadu, in the named week.
- **A5 must sit in a single card network** in the UK — a new authentication flow
  rolled out by one network. EV-099 asks about "one card network", and DV-040
  asks about UK card failures overall; both are answerable only if the effect is
  attributable to one network rather than to cards generally.
- **A2 must sit in a single handset model** at two Dubai showrooms. Under §1.7a
  the order's money is attributed entirely to its handset, so the model dimension
  is well defined for refunds.

### 1.1b Every order has one handset

The world is generated so that **every order carries exactly one handset line and
zero to three accessory lines. There are no accessory-only orders.**

This is what makes `GLOSSARY.md` §1.7a work: order-level money broken down by
model, storage or colour is attributed entirely to the order's handset, with no
apportioning, because there is always exactly one to attribute to. Questions that
depend on it: DV-047, EV-034, EV-048, EV-074, and every product-dimension
question in eval batch 3.

Accessories still exist as their own units (§2.2) and drive the attach rate
(§2.12); they simply never appear without a handset.

### 1.2 Entities the frozen questions require

Some questions test behaviour that only exists if the generator builds the world
a particular way. These are constraints, not observations.

| Requirement | Needed by | Why |
|---|---|---|
| **Two showrooms named "Kestrel Anna Nagar"** — one in Chennai, one in Madurai, **both in `IN-TN`** | DV-052 | DV-052 asks "What was captured GMV for Anna Nagar last month?" and must produce a **clarify**, not an answer. The ambiguity is entity-level: two showrooms share a name. Both sit inside `IN-TN`, so the `rm_tamil_nadu` role can see both — the question must clarify rather than resolve by scope. One showroom, or two in different regions, and the question stops testing anything |

| **A model named "Kestrel Onyx", and a colour named "Onyx Black" used on other models** | EV-034 | EV-034 asks "show me sales for Onyx last month" and must **clarify**, not answer. The ambiguity is entity-level: the token matches a model and a colour. If only one exists, the question resolves and stops testing anything |

The name collisions are realistic. Anna Nagar is a locality name found in more
than one Tamil Nadu city, and retailers name branches after localities. Phone
makers reuse material words — Onyx, Graphite, Midnight — as both model names and
finish names, which is exactly why the ambiguity bites in practice.

### 1.3 Named entities the questions require, and the test that enforces it

A question naming an entity the generated world does not contain is unanswerable,
and the failure looks exactly like a system bug. **M2's TEST must include a test
that loads every question file, extracts every named city, showroom, model,
colour, bank and network, and asserts each exists in the generated world.** It
runs against the real `data/` artifact; a missing entity fails, it never skips.

Entities named across `dev.jsonl` and `eval.jsonl` as of the eval freeze:

| Kind | Named |
|---|---|
| Country | India · UK · UAE · Singapore · Malaysia · US |
| Region | Tamil Nadu (`IN-TN`) |
| City | Chennai · Coimbatore · Madurai · Velachery · Anna Nagar · Dubai · Manchester |
| Showroom | **Kestrel Anna Nagar** ×2 — one in Chennai, one in Madurai (§1.2) |
| Model | **Kestrel Onyx** (§1.2) |
| Colour | **Onyx Black**, used on models other than Kestrel Onyx (§1.2) |
| Method | UPI · card · wallet · EMI · pay-later |

Notes on the ones that are not obvious:

- **Velachery** and **Anna Nagar** are Chennai localities. Velachery is used in
  EV-085 as an unambiguous entity, so it must exist as exactly **one** showroom
  or city; Anna Nagar must exist as **two** showrooms, which is the point of
  DV-052.
- **Manchester** appears in DV-037, a UNA question about staff. It still has to
  exist, or the question abstains for the wrong reason — "no such store" instead
  of "no staff data".
- **Coimbatore** and **Madurai** must be cities in `IN-TN` with showrooms, since
  EV-003, EV-022, EV-052 and EV-112 filter on them under the Tamil Nadu role.
- Issuing banks, acquiring banks and card networks are never named in a question
  — always asked for as a dimension — so the generator is free in its choice of
  names. The test should still assert the dimensions are non-empty.

### 1.2a EV-048: a global-level threshold is not achievable, and why

You asked that A2 clear the confirm gate at **global** refund level for August so
the agent could drill country → model. It cannot, at any realistic size.

A2 is a refund spike on one model at **two Dubai showrooms**. Those two are
roughly 4% of the UAE's 50 showrooms, and the UAE is a minority of global volume
— call the two showrooms **well under 1%** of global refunded amount. Moving the
global figure by the required 2% relative would need their refunds to rise by
**several hundred per cent**. That is not a defective batch; it is a recall large
enough to distort every other metric in the dataset, and it would corrupt the
unrelated questions that read UAE and global refund figures.

The gate is doing its job here: a genuinely local anomaly *should not* register
as significant globally, and a why-agent that confirmed it would be wrong.

**Proposed rephrasing — asked at the level where the anomaly is real:**

> EV-048 · `global_finance` · **"Why did the refund rate jump in Dubai in August?"**

At city level the two affected showrooms are a large share of the base, so a
plausible defective-batch spike — refunds at those showrooms roughly tripling —
moves Dubai's refund rate by well over 2% and clears |z| ≥ 2 comfortably. The
agent must still find **which showrooms** and **which model**; only the city is
given.

This keeps EV-048 distinct from DV-058, which asks at **country** level and
requires drilling country → model. EV-048 asks at **city** level and requires
drilling showroom → model. Different entry point, different drill path, same
anomaly.

| Question | Level named | Agent must find |
|---|---|---|
| DV-058 | UAE (country) | showrooms, model |
| EV-048 | Dubai (city) | showrooms, model, from a narrower base |

`test_anomaly_magnitudes_clear_thresholds` (M2) asserts this against the built
artifact rather than trusting the generator's parameters, and prints the realised
relative change and z for each anomaly at the granularity its question uses.

## 2. Sealed anomalies S1–S4

Types are known now and are public. **Parameters — network, country, model, city,
showroom, region, dates, magnitude — are drawn from the sealed seed in M2 and
written only to `eval/sealed/`.** The author does not open that directory before
G5; `test_sealed_read_only_by_scoring` enforces that only `evalkit.scoring` reads
it.

| Id | Type |
|---|---|
| S1 | Card success-rate dip for one card network in one country, lasting a few days. **The country draw excludes `GB`**, so S1 cannot collide with A5, which is a UK card-network effect. A holdout question and an eval question pointing at the same signal would make both unscoreable |
| S2 | Refund-rate spike on one phone model in one city |
| S3 | Order-volume drop at a single showroom for one week |
| S4 | EMI share **rising** in one region after a promotion |

S4 moves upward deliberately. A why-agent that assumes "explain the drop" will
miss it, and that is a real failure mode worth measuring.

## 2a. Realistic magnitude ranges for S1–S4, written before generation

The generator may only choose a magnitude inside these ranges. They are recorded
here **before** the sealed anomalies are drawn, so the bounds cannot be widened
later to make a stubborn candidate fit.

| Id | Effect | Realistic range | Why this range |
|---|---|---|---|
| S1 | Capture-rate multiplier for one card network | **0.45 – 0.80** | An authentication or routing fault degrades a network; below 0.45 the network is effectively down and would be noticed by other means |
| S2 | Refund-rate multiplier for one model in one city | **2.0 – 6.0** | A defective batch. Above 6× every unit sold is coming back, which is a recall rather than a batch |
| S3 | Order-volume multiplier at one showroom for a week | **0.25 – 0.70** | Refit, flood, local closure. Below 0.25 the showroom is shut, which the calendar would record |
| S4 | EMI-share multiplier in one region | **1.3 – 2.2** | A promotion moving customers onto instalments. Above 2.2 implies nearly everyone switched |

If no candidate clears the gate at its entry level within these ranges, the
generator **fails loudly** rather than widening them.

## 3. Holdout WHY questions are generated, not written

The generator writes **six** questions to `eval/sealed/holdout_why.jsonl`:

**Entry level is exactly one level above the cause (ADR-013).** No global
variants: three passes established that a local anomaly cannot move a global
metric at any realistic magnitude, and a question that cannot be answered is not
a test of anything.

| Id | Cause (to be found) | Entry level (named) | Count | The two metrics |
|---|---|---|---|---|
| S1 | card network | **country** | 2 | order-level success rate · attempt failure rate |
| S2 | phone model | **city** | 2 | refund rate · refunded amount, the amount only if it clears |
| S3 | showroom | **its city** | 1 | order count |
| S4 | acquiring bank or channel | **region** | 1 | EMI share |

Each question names **only the metric, the entry level, and the window**. It must never
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

---

## 4a. Standing rule: a round is not done until CI is green

**Local green is not green.** A round ends when CI on the *pushed commit* passes,
not when the suite passes on a laptop.

This rule exists because it was broken. CI on `main` was red from run #30
(`810cd75`) through `34561645195` — five consecutive runs — while three reports
said "tests green". They were green locally. Nobody looked at CI, and the two
causes were both things a laptop cannot see:

- `make data` used `/usr/bin/time -l`, a BSD flag. GNU `time` on the runner
  rejects it. macOS never would.
- The `test` job had no artifact, because it did not depend on `data`. The
  artifact tests correctly fail rather than skip, so they failed — on a machine
  where `data/` happened to exist locally, nothing was visibly wrong.

**Every report ends with:**

```
commit  <sha>
CI run  <id>
jobs    lint <status> · types <status> · data <status> · test <status> · freeze <status>
```

If the run is not green, the report says so in that block rather than anywhere
softer, and the round is not finished.

## 5. Notes for later modules

Things discovered while writing the questions that belong to a module not yet
built. Recorded here rather than lost.

### M7 — Tamil synonyms must carry the code-mixed form as well as the formal one

The semantic layer's `synonyms` for each metric and dimension must list **both**
Tamil forms:

1. the **formal Tamil term** — `திருப்பியளிப்பு விகிதம்`, `நிகர வருவாய்`,
   `செட்டில்மென்ட் தாமதம்`;
2. the **English term as it appears inside a Tamil sentence** — `refund rate`,
   `net revenue`, `settlement`, `GMV`, `EMI`, `UPI`, `attach rate`,
   `issuing bank`, `acquiring bank`, `order`, `showroom`, `storage`.

This is not a courtesy to English. It is how the language is actually written by
the people this product is for: a Chennai store manager types Tamil grammar with
English business nouns in Latin script, because that is what the nouns are called
at work. A layer that only knows `திருப்பியளிப்பு விகிதம்` will fail on
*"கடந்த மாதம் refund rate எவ்வளவு?"*, which is the more likely sentence of the
two — and it will fail by falling through to the free-form path, so the failure
will look like a retrieval miss rather than a vocabulary gap.

The Tamil question variants are drafted in exactly this register, so the eval
measures it either way. The term table at the top of
`eval/questions/_review/tamil_*.md` lists which terms are written in English and
which in Tamil; that table is the checklist for the synonym lists.

**Time words carry the same requirement, in one script.** The drafts use
`கடந்த வாரம்` / `கடந்த மாதம்` / `கடந்த ஆண்டு` throughout, but `சென்ற` is the
equally ordinary Tamil for "last" and a manager will type it. Both forms must
resolve:

| Window | Written in the drafts | Must also resolve |
|---|---|---|
| last week | `கடந்த வாரம்` | `சென்ற வாரம்` |
| last month | `கடந்த மாதம்` | `சென்ற மாதம்` |
| last year | `கடந்த ஆண்டு` | `சென்ற ஆண்டு` |

This is not a translation quibble. Under §1.6 "last week" and "the last 7 days"
are *different windows*, so a parser that fails to recognise `சென்ற வாரம்` does
not fall back to a near-synonym — it fails to find any window at all, and the
question either abstains or silently takes a default. Both are wrong, and only
one of them is visible.

Practical consequences:

- **Retrieval is lexical (ADR-004)**, so a missing surface form is a missing
  match — there is no embedding to bail it out.
- **Inflection erases the citation form.** Tamil is agglutinative: `சிங்கப்பூர்`
  never appears inside `சிங்கப்பூரில்`, and `ஆகஸ்ட்` never inside
  `ஆகஸ்டுக்கும்` — the final pulli is lost when a case ending attaches. Match
  stems, not dictionary forms. This is not hypothetical: the checker written to
  verify the drafts reported 16 false mismatches until it was fixed, and the
  semantic layer will hit the identical trap.
- **Both scripts, per term**, not one canonical choice. The same manager writes
  it both ways on different days.
- **The English forms are not synonyms of each other.** `issuing bank` and
  `acquiring bank` are different dimensions (§1.9), and a synonym list that maps
  both to "bank" reintroduces the confusion the glossary spent a section
  removing.

### M4 — a reference value of zero is compared exactly

`tolerance_rel` is a *relative* tolerance, so it is undefined against a reference
of zero: `abs(got - 0) <= 0.001 * 0` is `got == 0` for an exact float and a
false negative for anything else, and dividing by the reference to form a
relative error divides by zero.

**Rule: when the reference value is 0, compare exactly. No tolerance, absolute
or relative.** A zero reference is not a rounding target — it is a claim that the
quantity does not exist — so "close to zero" is the wrong test in both
directions: 0.4 units of currency is not zero, and there is nothing to be within
0.1% of.

This is not hypothetical. GLOSSARY §2.11 says EMI is offered only in India and
Malaysia, so **an EMI share for the UK or the UAE is legitimately zero rather
than missing**, and one holdout question (HO-043) asks for exactly that. The
distinction it tests is worth stating: a system that abstains there is wrong,
because the number is known and it is zero.

Two consequences beyond the scorer:

- **M3** must write reference SQL that returns a row containing 0, not zero rows.
  An empty result and a result of zero are different claims, and the scorer
  cannot tell them apart after the fact.
- **The same rule applies to a zero *component*** of a table answer — a country
  with no EMI inside an EMI-share-by-country result is an exact-zero cell, not a
  cell within tolerance.

*(This is the only place a holdout question is named in this file. It is here on
an explicit instruction, and it names the qid and the scoring rule, not the
question.)*

### M4 — list-valued answers are compared as sets

Some answers are a **list of things**, not a ranking and not a series: the
showrooms carrying a pending refund, the refund records still open at the
gateway, the countries where a condition holds. LIVE questions produce most of
them (§6.3: a gateway question asks for records, not a total).

**Rule: a list-valued answer is compared as a set.** Membership decides
correctness; order does not. Two answers with the same members in a different
order are the same answer, and a scorer that compares position by position marks
a right answer wrong for a reason the asker would not recognise as a reason.

This is distinct from the two ordered cases, and the three must not be
conflated:

| Answer shape | Compared how | Why |
|---|---|---|
| **Ranking** (`top_k`) | by position, tied values interchangeable | the order *is* the answer |
| **Series** (`series: true`) | by time key | the days must line up; their order is not in question |
| **List** (neither flag) | as a **set** | nothing in the question asked for an order |

A list answer therefore carries neither `top_k` nor `series`, which is how the
scorer tells the three apart. Where a list has a natural order — refund age,
say — a question that wants it says so, and that makes it a ranking.

### M4 — the top-k scorer and tied values

`evalkit/scoring.py` compares a table answer against the reference on the top-k
`(key, value)` pairs **in order** (SDD §25.3). Sparse metrics break that: if six
countries have duplicate captures and five of them are zero, any ordering of
those five is equally correct, and a scorer comparing position by position marks
five of six wrong for a right answer.

**Rule: tied values are interchangeable in order.** Ranks are compared as
**groups of equal value** — the set of keys at each distinct value must match,
and the order *within* a tie group is ignored. Order *between* groups still
matters.

**Question-writing consequence:** if more than half of a top-k would be ties at
zero, the question is a bad ranking regardless of how the scorer behaves, because
it is mostly asking the system to order noise. Shrink k, or ask something dense.
This was applied when writing eval: EV-012 and EV-058 began as rankings over
duplicate captures, a metric that is near-zero almost everywhere, and were
rewritten as scalars measuring different quantities.

### End of M3 — leakage protection for the holdout

**Apply at the end of M3, once the reference SQL exists.** Recorded now so it is
not forgotten at the point it stops being possible to do honestly.

The holdout runs **once**, at G5, and whatever it says gets published (PDD §5).
That only means anything if the questions and their answers were never available
while the system was being built. The risk is not deliberate cheating; it is the
ordinary drift of an assistant reading a file to be helpful, or an author
glancing at a reference query to debug something unrelated, and thereafter being
unable to un-know it.

**1. Deny reads at the tool level.** Add to `.claude/settings.json` permission
deny rules for `Read` on:

```
eval/questions/holdout.jsonl
eval/questions/holdout_blind*
eval/reference_sql/HO-*
eval/sealed/**
```

The point is that the block sits **outside** the thing being blocked. A rule the
assistant is asked to respect is a request; a rule the harness enforces is a
control.

**2. A charter test that nothing outside `evalkit` references those paths.**
An AST scan over `receipts/` and `kestrel_gen/` for string literals or path
constructions naming `holdout`, `holdout_blind` or `sealed`. Only
`evalkit.questions`, `evalkit.harness` and `evalkit.scoring` may name them, and
`eval/sealed/` only from `evalkit.scoring` — which SDD §6 already requires and
`test_sealed_read_only_by_scoring` already enforces.

Pair it with an injection: a module under `receipts/agent/` that reads
`eval/sealed/holdout_anomalies.json` must make the test fire, and a meta-test
must show it passes with the guard disabled.

**3. Both are worth stating in `LIMITATIONS.md`** — the mitigation and its limit.
Neither control proves the author never looked; they make looking a deliberate
act that leaves a trace, which is the most a repository can honestly claim.

### M10 / M12 — a capability refusal is a DENY, not an error

When free-form SQL is rejected because it touches a table outside the **role's
capability** allowlist — `settlements` or `settlement_items` for a role without
`finance` — the answer status must be **`DENIED`**, with a reason naming the
missing capability. Not `ERROR`, and not `ABSTAIN`.

The three are different claims about the world, and only one of them is true:

| Status | What it tells the asker |
|---|---|
| `ERROR` | Something broke. Try again, or report a bug |
| `ABSTAIN` | No data here can answer this |
| `DENIED` | The data exists and answers this; **you** may not see it |

A capability refusal is the third. Returning `ABSTAIN` would be a lie of a
particular kind — it tells a UK store manager that settlement fees are
unknowable, when in fact they are known and simply not theirs. Returning `ERROR`
sends them to a bug report for a working system.

The verified path already handles this: the gate denies at rule 1 (SDD §10) before
compilation. The gap is the **free-form** path, where the refusal surfaces from
the guard rather than the gate, and a guard rejection currently maps to
`GUARD_REJECTED`.

**Fault injection required:** a `store_ops_uk` question about settlement fees —
HO-025 is exactly this — routed down the free-form path must produce `DENIED`
naming the `finance` capability, with a meta-test showing it produces something
else when the capability check is disabled.

### M21 — publish the sealed files and the seed after the holdout

`eval/sealed/` is untracked and the freeze records only SHA-256 hashes of its
contents (ADR-012). That is the right posture *while building*, and the wrong one
afterwards: a holdout nobody can inspect is a claim, not a result.

**At G5, once the holdout has run its single time, commit the sealed files and
publish the seed** currently in `.env`. Then anyone can regenerate the world,
re-derive S1–S4, and check the scoring for themselves.

Verify the recorded hashes first. If a sealed file no longer matches the hash
taken at `gen-frozen`, the holdout was scored against something other than what
was sealed, and the result is void — say so rather than publishing it.

This is written down now, before the numbers exist, because the incentive not to
publish only appears afterwards.

### M12 — free-form SQL can reach `orders.customer_id`

EV-039 was drafted as an unanswerable question about repeat customers, on the
assumption that customer data is out of reach. It is not: `orders.customer_id`
exists on a table the free-form path can query, so a free-form answer could count
repeat customers even though `customers` is excluded from the semantic layer and
from every allowlist.

The semantic layer is safe — no metric or dimension exposes it. The gap is the
`UNVERIFIED` free-form path, which is allowed to select columns the layer does
not expose.

**Consider a column-level denylist in the AST guard**, not just a table-level
allowlist, so `customer_id`, `phone_masked` and `email_hash` cannot be selected,
grouped by, or joined on from any path. That is a real design decision with a
cost — the guard currently reasons about tables only — so it **needs an ADR**
before it is built.

The question itself was replaced (EV-039 now asks about warranty claims, which
genuinely do not exist in the schema), so the eval is not relying on the gap.
