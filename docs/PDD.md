# Receipts — Product Definition Document

**Version** 1.2 (review round 1 of 2)
**Changes in 1.2** front end reduced to one screen (Vite + React SPA served by the API); Evals and Audit pages removed; cut order renumbered
**Changes in 1.1** data history now ends 9 Sep 2026 with a fixed, injected "today"; the business glossary is the single source of metric definitions; sealed holdout anomalies added
**Date** 10 September 2026
**Owner** Nandesh K
**Companion docs** SDD (next), BUILD_PROMPTS (after SDD), `docs/diagrams/receipts_platform_architecture.svg`, `docs/diagrams/receipts_agent_pipeline.svg`

> Review rule, carried over from Abstain: two review rounds on this document, then build. When a round finds only wording, stop reviewing.

---

## 1. One-line definition

Receipts lets anyone in a retail business ask questions about sales and payments in their own language, and every answer comes with a receipt: the exact metric definition, scope, time window, and data it was computed from, so a person who cannot read SQL can still tell whether the number is right.

---

## 2. The problem

Text-to-SQL demos fail in the most expensive way possible: **silently**. They return a confident, well-formatted, wrong number, and the person asking has no way to notice.

The failures are rarely syntax errors. They come from definitions that the schema doesn't state, and in payments data those definitions are everywhere.

**Worked example.** *(Numbers are illustrative and will be replaced by real generator output at gate G1.)*

A regional manager for Kestrel Mobile asks: *"What was our UPI success rate in Chennai yesterday?"*

On 9 September 2026 (IST), Chennai's 14 showrooms had 4,120 orders where the customer tried UPI. Customers retry, so those orders produced 5,412 payment attempts. 3,848 orders were eventually paid.

| Interpretation | Result |
|---|---|
| Order-level: an order succeeds if any attempt succeeds | **93.4%** (3,848 / 4,120) |
| Attempt-level: successful attempts over all attempts | **71.1%** (3,848 / 5,412) |
| What a free-form SQL query typically produces: attempt-level, UTC day boundaries (5.5 hours off), test transactions included | a third number, shown with equal confidence |

All three are "the UPI success rate." The manager sees one of them, with no indication that a choice was made. A 71% reading causes a real escalation; a 93% reading is a normal Tuesday.

A second example: *"Total revenue last month?"* across six countries. A naive query sums INR, AED, SGD, MYR, GBP and USD amounts stored in minor units, producing a number that is not money in any currency.

These aren't edge cases. Attempts vs orders, authorised vs captured, partial refunds, local vs UTC time, the Indian fiscal year starting in April, capture date vs settlement date, test transactions in production tables: **every one of them is a silent wrong answer waiting to happen**, and every one is familiar to anyone who works on payments.

---

## 3. Who it's for

| Persona | Needs | Can't do |
|---|---|---|
| **Regional sales manager** (Chennai, Tamil-first) | Quick answers on the showroom floor, on a phone | Write SQL; judge whether a query is correct |
| **Finance / settlements analyst** | Refunds, settlement lag, unsettled cash, reconciliation questions | Wait two days for the data team |
| **Store operations lead** | Payment failures by method, bank, and store; "why did this drop?" | Diagnose across five dimensions by hand |
| **Data / platform admin** | Define metrics once, control who sees what, audit everything | Review every generated query |
| **External agent** (Claude Desktop, IDE) | Governed tools over MCP instead of raw database access | Be trusted with unrestricted SQL |

---

## 4. What it does

The loop for a single question:

1. **Understand.** Detect the language (Tamil, Hindi, English, or code-mixed) and classify the intent.
2. **Plan.** The model turns the question into a typed `QueryPlan` (metric, dimensions, filters, time window, grain) chosen from a governed semantic layer. **It never writes SQL on this path.**
3. **Check.** Deterministic validation: the metric exists, the dimensions are legal for it, and time resolves to explicit local-time bounds and the correct calendar.
4. **Decide.** A gate either proceeds, asks one clarifying question, abstains ("no data here can answer that"), or denies ("outside your scope").
5. **Compile.** Deterministic compiler: plan → dialect-specific SQL, with the user's row-level scope injected. The model never sees or controls this filter.
6. **Execute.** An AST guard, read-only role, row limit, and timeout, then run on the right adapter.
7. **Answer.** Narrate in the asker's language, pick the chart from the result's shape, and attach the receipt.
8. **Explain (optional).** "Ask why" launches a bounded agent loop that breaks the change down by dimension and reports the largest contributors, stating clearly that these are contributors, not proven causes.

Questions the semantic layer can't express fall back to free-form SQL. They still pass through the same guard and scope injection, and the answer is visibly marked **Unverified**.

---

## 5. The thesis (non-negotiable)

> **Claim:** Constraining the model to produce a typed plan over a governed semantic layer, compiled deterministically, reduces *silent* wrong answers on business questions by at least half compared with a strong free-form text-to-SQL baseline using the same model and the same metric documentation, while keeping coverage of answerable questions within 10 points.

This is a measurement, not a capability demo. If the baseline turns out nearly as safe, that is a finding and it gets published.

**What would falsify it:** Receipts' silent-wrong rate on the held-out set being more than half the baseline's.

**Rules that follow, and what we will not do to make the result look better:**

- **The baseline gets the definitions too.** It receives the full schema DDL, column comments, every metric definition from the business glossary (`docs/GLOSSARY.md`) as text, 10 few-shot examples, one retry on SQL errors, and permission to answer `CLARIFY` or `CANNOT_ANSWER`. We are testing the architecture, not whether one side knew what "success rate" means.
- **Same model, same temperature, same questions** for both systems.
- **Questions are written before the semantic layer.** The eval questions are frozen at G1, before any metric YAML exists, so the layer can't be shaped around the test.
- **At least 20% of questions fall outside the semantic layer on purpose.** Receipts must fall back, clarify, or abstain on them, and those outcomes are scored.
- **The held-out set runs once.** Whatever it says gets published. Nothing is tuned afterwards.
- **Abstaining is not free.** Over-abstention on answerable questions is its own metric with its own threshold, so the system can't win by refusing everything.

---

## 6. Taxonomy

### 6.1 Question classes

| Class | Example | Handled by | Nature |
|---|---|---|---|
| Q1 Direct metric | "Captured GMV in UAE in August" | Plan → compile | Deterministic after planning |
| Q2 Breakdown / ranking | "Top 5 showrooms by refund rate this quarter" | Plan → compile | Deterministic after planning |
| Q3 Time comparison | "This month vs last month, by country" | Plan → compile | Deterministic after planning |
| Q4 Definitional trap | "UPI success rate", "revenue", "last quarter" | Semantic layer + gate | Deterministic definition, may need a clarify |
| Q5 Multi-hop | "Average settlement lag for EMI orders by acquiring bank" | Plan → compile (joins in the layer) | Deterministic after planning |
| Q6 Ambiguous | "Which is our best store?" | Gate → clarify | Judgement |
| Q7 Unanswerable | "Customer satisfaction in Pune", "predict next month" | Gate → abstain | Judgement |
| Q8 Diagnostic | "Why did UPI success drop in Chennai on Tuesday?" | Why-agent loop | Judgement over deterministic sub-plans |
| Q9 Live / cross-source | "Which refunds from last week are still pending at the gateway?" | Tool Bridge + DB | Deterministic tool calls |
| Q10 Out of scope for the user | Chennai manager asks about UAE | Compiler scope → deny | Policy, deterministic |

The expected finding, as with Abstain, is a lopsided split: most of the work is deterministic once the plan exists, and the model's real job is narrow (understanding language, choosing the plan, narrating). That narrowness is a result, not a weakness.

### 6.2 Definitional traps the semantic layer must encode

Each trap becomes at least three eval questions, in at least two languages.

| Trap | Correct rule in Receipts |
|---|---|
| Attempts vs orders | Success rate defaults to order-level; attempt-level is a separate named metric |
| Authorised vs captured | Revenue counts captured only |
| Partial refunds | Net revenue = captured − refunded, by refund date or capture date (declared per metric) |
| Multi-currency | Amounts stored in minor units per currency; cross-country totals convert at the daily FX rate into a declared reporting currency |
| Local time | "Yesterday" means the showroom's local day, not UTC |
| Fiscal calendar | "Q2" or "this quarter" is ambiguous in India (FY starts April); the gate clarifies unless the user has a saved preference |
| Capture vs settlement | Settlement metrics key on settlement date |
| Test transactions | Excluded everywhere via a flag, never by name matching |
| EMI | Order value, not instalment value, unless the metric says otherwise |
| Duplicate captures | Counted once for GMV; visible in a dedicated metric |

---

## 7. The synthetic world: Kestrel Mobile

A fictional phone brand. **All data is synthetic, generated by a seeded, frozen generator.** No real company data, schemas, or configurations are used anywhere.

- **Footprint:** about 480 showrooms across India, UAE, Singapore, Malaysia, the UK and the USA, plus an online-order, in-store-pickup channel.
- **Catalogue:** about 40 phone models with storage and colour variants, plus accessories (so attach rate is askable).
- **History:** 18 months, March 2025 to 9 September 2026. The world's "today" is fixed at 10 September 2026 and injected as a parameter, never read from a clock. Target volume is around 7M orders and 10M+ payment attempts; the realised counts are asserted at G1, not promised here.
- **Payments:** UPI (India only), cards by network and issuing bank, netbanking, wallets, EMI (India and Malaysia), with realistic retries, failure reasons, partial refunds, settlements with lag, and daily FX.
- **Storage:** operational tables in PostgreSQL; the analytical copy in Parquet queried through DuckDB.

**Planted anomalies**, recorded as ground truth at construction time, never re-derived:

| ID | What was planted | Question it enables |
|---|---|---|
| A1 | UPI success dip for one issuing bank in Tamil Nadu on one date | "Why did UPI success drop in Chennai?" |
| A2 | Refund spike on one model at two Dubai showrooms (defective batch) | "Why are UAE refunds up?" |
| A3 | Settlement delay for one acquiring bank's EMI transactions in one week | "Why is unsettled cash high?" |
| A4 | Launch-week sales surge for one model in Singapore | "What drove Singapore's August?" |
| A5 | Card decline spike in the UK after a simulated authentication change | "Why did UK card failures jump?" |
| A6 | Duplicate captures at one showroom, later refunded | "Any stores with unusual refund patterns?" |
| A7 | Test transactions left in the production table | Every trap question that counts payments |
| A8 | A product note field containing a prompt-injection string | Security test, not analytics |
| S1–S4 | Sealed anomalies: types known, but bank, city, date and size drawn from a sealed seed and written only to a truth file the author doesn't open before G5 | Holdout why-questions |

---

## 8. Product surfaces and key journeys

### 8.1 Surfaces

The web front end is **one screen**. It exists to show a non-technical user getting a trustworthy answer, nothing more.

- **Ask.** Chat on one side, the answer on the other. Agent steps stream live. Every answer carries its receipt, a status badge, a chart with a table view, and "Ask why." Clarifications appear as one-tap choices.
- **Receipt drawer.** Opens from any answer: the SQL, the plan, and the step trace. Linkable with `?receipt=<id>`.
- **Catalog drawer.** Browse every metric's definition and dimensions. Doubles as the fallback form when the model is unavailable.
- **Header.** Role switcher (one click to become "Chennai regional manager", "Global finance", "UK store ops" or "Admin", so a reviewer can see scoping work within a minute) and language toggle.
- **MCP.** The same governed tools, available in Claude Desktop or any MCP client.

There are no Evals or Audit pages. Eval results live in the README and the committed report files; the audit log is available to admins through the API.

### 8.2 Answer statuses

| Status | Meaning |
|---|---|
| **Verified** | Answered from a validated plan over governed metrics |
| **Clarify** | Needed one choice from the user before answering |
| **Unverified** | Answered with free-form SQL outside the layer; flagged in the UI and receipt |
| **Abstain** | No available data can answer it; says what data would be needed |
| **Denied** | Outside the user's scope; logged |

### 8.3 Journeys that must work end to end

| # | Journey | Pass condition |
|---|---|---|
| J1 | Chennai manager asks in Tamil about UPI success yesterday | Tamil answer, order-level metric, IST day, receipt present |
| J2 | Finance asks "why is unsettled cash high?" | Why-agent surfaces A3 as top contributor within 6 steps |
| J3 | "Best store last quarter?" | One clarifying question (metric and fiscal vs calendar), then answer |
| J4 | "Customer satisfaction in Pune?" | Abstain, naming the missing data |
| J5 | Chennai manager asks about UAE | Denied, logged, no UAE numbers anywhere in the response or trace |
| J6 | Same question from Claude Desktop over MCP | Same plan, same number, same receipt ID format |
| J7 | Model provider down | UI switches to catalog mode; saved questions still run; clear banner |
| J8 | Admin adds a metric in YAML | Available after reload with no code change; lint passes in CI |
| J9 | "Pending refunds at the gateway from last week" | Tool Bridge call to the mock gateway joined with DB orders |
| J10 | Follow-up: "now split by city" | Previous plan reused and refined, not re-planned from scratch |

---

## 9. Engineering bars: the all-rounder spec

Each area gets something concrete to build and a bar that can be checked against an artifact.

| Area | What we build | The bar |
|---|---|---|
| **Frontend** | Vite + React + TypeScript + Tailwind single-page app, served by the API. One Ask screen with receipt and catalog drawers, streaming trace, chart with table view, role switcher | Works at 375px wide; keyboard-complete; WCAG AA contrast; every chart has a table view; Playwright covers J1, J3, J4, J5, J7, J10 |
| **Backend** | FastAPI (async), Pydantic models, SSE streaming, MCP server over Streamable HTTP, OpenAPI docs | Typed end to end (mypy strict on core); a typed error code for every failure path; no endpoint returns a bare 500 |
| **AI / agent** | Intent router, catalog retrieval, structured-output planner, gate, composer, bounded why-agent, versioned prompts | Every model call has a schema, a prompt version, a token budget, and a record/replay fixture |
| **Data** | Seeded generator with planted anomalies and constructed truth; Postgres + DuckDB/Parquet; semantic layer YAML with a linter | Same seed gives byte-identical data; the generator and the engine share no code (enforced by test); every metric has a definition, owner, and at least one test question |
| **Multi-DB** | Adapters for PostgreSQL and DuckDB; dialects through sqlglot; MySQL conditional | The same plan returns identical results on both adapters for every overlapping table (tested) |
| **Security** | Compile-time RBAC predicates, read-only DB role, AST guard, PII-free semantic layer, prompt-injection handling, rate limits, secrets from env | **Zero** leaks and **zero** successful writes under the fault-injection suite; THREAT_MODEL.md committed |
| **Observability** | OpenTelemetry trace per question, span per stage, token and cost metering, append-only audit log | Any receipt ID reconstructs the full trace, plan, SQL, and row count |
| **Reliability** | Fallback model provider, catalog mode on outage, DB timeouts with clear messages | Chaos tests: kill the model → catalog mode works; kill DuckDB → typed error, no hang |
| **Performance & scale** | Plan cache, result cache tied to freshness, 10M+ row warehouse, committed benchmark script | Latency thresholds in §10 met and printed by the benchmark |
| **Cost** | Catalog subset in the prompt instead of the full schema; per-question token budget | Median tokens and cost per 1,000 questions reported for both systems |
| **Internationalisation** | Tamil, Hindi, English, and code-mixed input; Indian digit grouping (₹12,34,567); per-locale currency display | Language parity threshold in §10 |
| **DevOps / CI** | Docker Compose, `make up`, GitHub Actions: lint, types, tests, dev-set eval on replayed responses, image build; live deployment with demo roles | Fresh clone to working app in three commands or fewer; CI is green and makes zero network calls |
| **Testing** | Unit, property-based compiler tests, fault injection for every guard, golden evals, E2E | Every guard is paired with an injection that makes it fire |
| **Documentation** | README (results first), ARCHITECTURE.md with both diagrams, SEMANTIC_LAYER.md, THREAT_MODEL.md, LIMITATIONS.md, short ADRs for key decisions | Every number in the README traces to a committed artifact |
| **Product writing** | Plain-language receipts, errors that say what happened and what to do next | No error message says only "something went wrong" |

---

## 10. Pre-declared thresholds

Committed to `config/thresholds.yaml` at G0, before any engine code exists. "Silent wrong" means answered, not flagged as Unverified, and wrong.

| ID | Measure | Threshold | If breached |
|---|---|---|---|
| T1 | Receipts silent-wrong rate (eval set) | ≤ 3% | Diagnose by class before adding features |
| T2 | **Thesis:** Receipts silent-wrong ÷ baseline silent-wrong (holdout) | ≤ 0.5 | Publish as the headline result regardless |
| T3 | Accuracy on answerable questions | ≥ 85% | Publish; list failing classes in LIMITATIONS |
| T4 | Correct clarify/abstain on Q6/Q7 questions | ≥ 80% | Publish |
| T5 | Over-abstention on answerable questions | ≤ 10% | Publish; gate tuning allowed on eval set only |
| T6 | Tamil and Hindi accuracy vs English | within 7 points | Publish per-language numbers |
| T7 | RBAC leaks under fault injection | **0** | **Ship-blocking** |
| T8 | Successful writes or DDL through any path | **0** | **Ship-blocking** |
| T9 | Why-agent: planted anomaly as top-ranked contributor | ≥ 70% of planted-anomaly questions (A1–A6 on eval, sealed S1–S4 on holdout) | Publish; cut from demo if below 50% |
| T10 | Latency, single-metric questions on the full warehouse | p50 ≤ 4s, p95 ≤ 10s | Publish measured values |
| T11 | Run-to-run variance, three eval runs | ≤ 2 points on T1 and T3 | Report the mean and range |

Latency (T10) and variance (T11) are hypotheses about hardware and model behaviour; they're declared now so the measured values mean something later.

---

## 11. Evaluation design

**Question sets** (frozen at G1, hashes recorded in a manifest):

| Set | Size | Rule |
|---|---|---|
| Dev | 60 | Run freely while building |
| Eval | 150 | Iterate against it; membership is fixed |
| Holdout | 90 | Run **once**, at G5. Includes 30 questions written blind by someone other than the author |

The default `make eval` target points at **dev**, never the holdout.

**Languages:** every eval and holdout question exists in English, Tamil, and Hindi. At least 20% are code-mixed (Tanglish, Hinglish). Translations are human-written or human-verified and labelled as such.

**Reference answers:** planted-anomaly questions are scored against constructed truth. All others use hand-written reference SQL that follows the glossary, reviewed once, and never generated by either system under test. Twenty questions are also computed by a second, independent method (pandas over Parquet) and must agree.

**Scoring outcomes, per question:** Correct · Wrong-flagged · **Silent-wrong** · Correct-clarify · Correct-abstain · Over-abstain · Leak. Numeric answers pass within 0.1% relative tolerance; rankings must match the top-k in order.

**Systems compared:**
- **B0 (baseline):** strong free-form text-to-SQL, configured as in §5.
- **Receipts:** the full pipeline.
- **Ablations** (conditional): Receipts without the gate; Receipts with free-form fallback disabled.

**Offline and reproducible:** model responses are recorded once and replayed. CI and `make eval` make zero network calls. Live-model runs are a separate target, reported with variance.

**The headline sentence:**

> *On 90 held-out payment-analytics questions in three languages, Receipts gave a silently wrong answer X% of the time; a strong free-form text-to-SQL baseline using the same model and the same metric documentation did so Y% of the time.*

---

## 12. Result language, pre-written

**If the thesis holds:**
"Constraining the model to a typed plan cut silent wrong answers from Y% to X% on held-out questions, with coverage within Z points. The model's job ended up narrow: understanding language, choosing a plan, and narrating. Correctness came from the semantic layer and the compiler."

**If it's mixed:**
"Receipts reduced silent wrong answers, but by less than the 50% we declared (ratio R). Most remaining errors were in [class]: the plan was valid but the wrong metric was chosen. That points to retrieval, not compilation, as the next bottleneck."

**If it's null:**
"A strong baseline given the same metric definitions was about as safe as the constrained pipeline (Y% vs X%). The definitions did the work, not the architecture. The remaining case for Receipts is governance (scoping, audit, receipts) rather than accuracy, and we report it on those terms."

---

## 13. Scope

### Core (never cut)
Generator with planted anomalies and constructed truth · question sets and harness · baseline B0 · semantic layer v1 (about 15 metrics) · planner, validator, gate, compiler, guard, executor · PostgreSQL and DuckDB adapters · RBAC scope injection · FastAPI with SSE · Ask page with chart, receipt, and statuses · Tamil, Hindi, English · MCP server · README with real numbers · LIMITATIONS.md

### Conditional, with a fixed cut order (first item goes first)
1. MySQL adapter
2. Grafana dashboards (the in-app trace viewer stays)
3. Ablation runs
4. Tool Bridge gateway journey (J9)
5. Why-agent loop (J2)

If any gate slips by more than a day, the next item on this list is cut. The order is fixed now and honoured later.

### Out of scope
Actions or writes of any kind (initiating refunds, editing data) · forecasting or ML predictions · real payment-gateway data or production APIs · model fine-tuning · voice input · SSO · Kubernetes · more than three database adapters · a dashboard builder

---

## 14. Calendar gates

Working backwards from submitting the application on **Saturday 26 September 2026**.

| Gate | Date | Required output | Cut rule if missed |
|---|---|---|---|
| **G0** | Sat 12 Sep | PDD, SDD, and build prompts frozen and hashed; `thresholds.yaml` and `GLOSSARY.md` committed; question set v1 drafted *before* any metric YAML | Freeze whatever exists; no third review round |
| **G1** | Tue 15 Sep | Generator frozen with A1–A8 and constructed truth; question sets frozen and hashed; harness running; baseline B0 scored on dev | Cut conditional item 1 |
| **G2** | Fri 18 Sep | Core pipeline end to end from the CLI; eval-set scores for Receipts vs B0 | If Receipts is not ahead of B0 on the eval set, **stop feature work and diagnose**. This is the thesis. |
| **G3** | Mon 21 Sep | API with SSE, MCP server, Ask page, receipts, RBAC, three languages | Cut items 2–3 |
| **G4** | Wed 23 Sep | Why-agent, Tool Bridge journey, observability, outage mode; live deployment | Cut items 4–5 in order |
| **G5** | Fri 25 Sep | Holdout run once; clean-room verification from the public URL; README and LIMITATIONS written | Nothing ships without the clean-room pass |
| **G6** | Sat 26 Sep | Three-minute demo video recorded; application submitted | Submit anyway, with Abstain pinned alongside |

---

## 15. Risks and mitigations

| Risk | Mitigation |
|---|---|
| **The author writes both the questions and the semantic layer**, biasing the eval toward Receipts | Questions frozen before the layer exists; 20% deliberately outside it; 30 holdout questions written blind by someone else |
| Model non-determinism makes numbers unrepeatable | Temperature 0, recorded responses, three live runs with variance reported (T11) |
| Translations come out stilted or machine-like | Human-written or human-verified, labelled per question; code-mixed questions included because that's how people actually type |
| The synthetic data is too clean to be interesting | Retries, partial refunds, FX, timezones, test rows, and duplicates are all generated; anomalies are planted, not obvious |
| Scope creep toward the "every box" architecture | The cut order in §13 is binding; a gate slip automatically removes the next item |
| The live demo gets abused or runs up cost | Demo roles only, rate limits, per-question token budget, spend cap on the API key |
| The why-agent overclaims causation | Output is labelled "largest contributors"; causal language is banned in the composer prompt and checked by test |

---

## 16. What the reviewer sees in two minutes

The Razorpay page promises a call within 48 hours "if it has signal." The repository is built to be read in this order:

1. **README first line:** the headline sentence from §11, with real numbers.
2. **A 20-second GIF:** a Tamil question → streaming steps → answer with receipt → "Ask why" finding the planted cause.
3. **A live URL** with a "try as Chennai manager" button.
4. **The results table:** Receipts vs baseline, by question class and language.
5. **Both architecture diagrams.**
6. **LIMITATIONS.md**, written at full resolution. A reviewer who reads an honest limitations section trusts the numbers above it more.

The application links this repository with Abstain pinned beside it. Together they make one argument: *the model proposes, a deterministic layer decides, and the system says so when it isn't sure.*
