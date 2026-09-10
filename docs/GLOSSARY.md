# Kestrel Mobile — Business Glossary

**Status** Official. These are the company's metric definitions.
**Owner** Payments Analytics
**Written** G0, before any semantic-layer YAML exists.

This document is the single source of metric definitions. Three things are built
from it and must agree with it: the hand-written reference SQL used to score the
evaluation, the free-form baseline's prompt, and the governed semantic layer.
Where an implementation and this document disagree, this document wins and the
implementation gets fixed.

Plain English throughout. No SQL, deliberately — a definition that can only be
read as SQL is not a definition a store manager can check.

---

## 1. Conventions that apply to every metric

### 1.1 What is always excluded

**Test transactions.** Kestrel's payment systems write test orders and test
payment attempts into the same tables as real ones. Every table that can carry
them has a test flag, and **every metric excludes them, always**. There is no
report, no filter, and no user setting that includes test transactions. They are
excluded by the flag, never by matching on names, amounts, or customer details.

**Nothing else is excluded by default.** Cancelled and abandoned orders are real
business events and are counted wherever the definition says to count them.

### 1.2 Which date a metric is keyed on

Every fact row carries a **business date**: the calendar date in the *showroom's*
local timezone at the moment the event happened. Metrics are keyed on a business
date, never on a UTC timestamp, unless the definition explicitly says otherwise.

Three different dates appear in this glossary, and mixing them up is the most
common source of a wrong number:

| Date | Meaning | Used by |
|---|---|---|
| **Order business date** | Local date the order was created | Order and unit metrics |
| **Capture business date** | Local date the money was captured | Revenue metrics |
| **Refund business date** | Local date the refund was processed | Refund metrics |
| **Settlement date** | Date the acquiring bank settled the money | Settlement metrics |

A refund issued in September against an order paid in August belongs to
September for refund metrics and to August for revenue metrics. Both are correct;
they are answers to different questions.

### 1.3 Money and currency

Amounts are stored in the **minor unit** of the currency they were taken in —
paise for INR, fils for AED, cents for GBP, USD, SGD, and MYR. A number stored
against an order is only meaningful together with that order's currency.

Amounts in different currencies are **never added together as raw numbers**.
Adding Indian paise to British pence produces a figure that is not money in any
currency.

When a question spans more than one currency, every amount is converted into a
single **reporting currency** at the daily foreign-exchange rate for that amount's
own business date — not today's rate, and not the rate on the last day of the
window. Conversion happens once, at the end, and the result is rounded to the
minor unit of the reporting currency.

### 1.4 The reporting-currency rule

The reporting currency for an answer is decided in this order, and the first rule
that applies wins:

1. The currency the asker named in the question.
2. The default reporting currency for the asker's role — Indian regional roles
   report in INR, UK store operations in GBP, global finance in USD.
3. If every country in the result shares one currency, that currency.
4. Otherwise, US dollars.

Whenever the reporting currency was **not** stated in the question, the answer
must say which currency it used and why. A currency chosen by default and not
disclosed is a wrong answer even when the arithmetic is right.

### 1.5 Fiscal year

Kestrel's **fiscal year starts on 1 April** and is named for the calendar year it
ends in: FY2026 runs 1 April 2025 to 31 March 2026. Fiscal quarters are
Q1 April–June, Q2 July–September, Q3 October–December, Q4 January–March.

The calendar year and calendar quarters also exist and are also legitimate. This
means **"Q2" and "this quarter" are ambiguous at Kestrel** and must be clarified
unless the asker has a saved preference. See §4.6.

### 1.6 Week

A week starts on **Monday** and ends on Sunday. "Last week" means the most recent
complete Monday-to-Sunday week, not the last seven days. "The last 7 days" means
the seven days ending yesterday, and is a different window.

### 1.7 "Yesterday", "today", and the local day

**"Yesterday" means the showroom's own local business date, one day before the
reporting date.** For a Chennai showroom on 10 September 2026 that is 9 September
in Indian Standard Time — not the 24 hours before midnight UTC, which would start
at 5:30 a.m. Chennai time and pull in five and a half hours of the wrong day.

When a question spans countries, "yesterday" resolves per showroom in that
showroom's own timezone. Every showroom's 9 September is included, even though
they are different absolute moments.

The reporting date is a fixed, injected date. It is never read from a system
clock, so the same question asked against the same data always covers the same
window.

### 1.8 Freshness

Data covers business dates from 1 March 2025 to 9 September 2026 inclusive. The
reporting date is 10 September 2026. A window that runs past the last loaded
business date is trimmed to it, and the answer says so.

### 1.9 Attributing an order to a payment method or bank

An order can carry payment attempts on different methods and different banks: a
customer whose card is declined may retry with UPI, or switch to a second card.
Any **order-level** metric broken down by method, card network, or issuing bank
therefore needs a rule for which one the order belongs to.

**Kestrel's rule:** an order is attributed to the method, card network, and
issuing bank of its **final payment attempt** — the attempt that decided the
outcome. For a paid order that is the capture. For an unpaid order it is the last
attempt the customer made before giving up.

This applies consistently to every order-level breakdown, including order-level
success rate by bank or by method (§2.8). Without it, an order with a failed
card attempt and a successful UPI attempt would be counted as both a card failure
and a UPI success, and per-bank rates would not reconcile to the overall rate.

**Attempt-level metrics need no attribution rule** (§2.9, §2.10): every attempt
already carries its own method, network, and bank. This is a second reason the
attempt-level and order-level breakdowns differ, on top of retries.

---

## 2. Metric definitions

### 2.1 Orders count

**What is counted:** the number of orders created in the window, of any status —
paid, abandoned, or cancelled.

**Denominator:** not a ratio.

**Date key:** order business date.

**Currency:** none; this is a count.

**Excluded:** test orders.

**Note:** because this counts every status, it is larger than the number of orders
that produced revenue. "How many orders did we take" and "how many orders did we
get paid for" are different questions; the second is the paid-order count used as
the denominator of average order value (§2.6).

---

### 2.2 Units sold

**What is counted:** the total quantity of items across the lines of **paid**
orders in the window. Two of the same phone on one order counts as two units.

**Accessories are included.** A "unit" at Kestrel is any item on an order line —
a phone, a case, or a charger each count as one unit. This means units sold is
always larger than phones sold, and a showroom with a strong accessory business
ranks higher on units than on handsets. When someone means handsets only, the
question has to say so, and the phones-only figure is a filtered version of this
metric rather than a separate one.

**Denominator:** not a ratio.

**Date key:** order business date of the order the line belongs to.

**Currency:** none; this is a count.

**Excluded:** test orders; lines belonging to abandoned or cancelled orders.

---

### 2.3 Captured GMV

**What is counted:** the total value of money actually **captured** from customers
in the window.

An authorised payment is not captured money. Authorisation means the bank has
reserved the funds; capture means Kestrel has taken them. Authorisations that are
never captured — because the customer abandoned the order, or the authorisation
expired — contribute nothing to captured GMV.

Where the same money has been captured more than once by mistake (§4.10), it is
counted **once**.

**Denominator:** not a ratio.

**Date key:** capture business date.

**Currency:** money. Amounts are converted to the reporting currency at the daily
rate for each amount's own capture business date.

**Excluded:** test payment attempts; authorised-but-not-captured attempts; failed
attempts; the duplicate side of a duplicate capture.

**Note:** captured GMV is a gross figure. It does not subtract refunds. For the
figure net of refunds, see net revenue (§2.5).

---

### 2.4 Refunded amount

**What is counted:** the total value of refunds **processed** in the window.
Refunds that are still pending, or that failed, are not counted.

Partial refunds count for the amount actually refunded, not the value of the
original order.

**Denominator:** not a ratio.

**Date key:** refund business date — the local date the refund was processed, not
the date of the order being refunded.

**Currency:** money, converted at the daily rate for each refund's own refund
business date.

**Excluded:** test transactions; pending and failed refunds.

---

### 2.5 Net revenue

**What is counted:** captured GMV in the window, minus refunds processed in the
same window.

**This is a deliberate choice and it matters.** The refunds subtracted are the
ones *processed* in the window, not the refunds that eventually attach to the
orders captured in the window. A refund processed in September against an August
capture reduces September's net revenue, not August's. The alternative — holding
each month open until every possible refund has landed — would mean no month ever
closes.

Net revenue can be negative for a narrow window, a single showroom, or a single
model, if refunds processed there exceed captures. That is a real result, not an
error.

**Denominator:** not a ratio.

**Date key:** capture business date for the captured side; refund business date
for the refunded side.

**Currency:** money, converted per side at each amount's own date, then
subtracted in the reporting currency.

**Excluded:** test transactions; pending and failed refunds; the duplicate side of
a duplicate capture.

---

### 2.6 Average order value

**What is counted:** captured GMV divided by the number of orders that produced
it.

**Denominator:** the count of distinct **paid** orders in the window — orders with
at least one captured payment. Abandoned and cancelled orders are not in the
denominator, because they contributed nothing to the numerator; including them
would understate the average.

**Date key:** capture business date, for both numerator and denominator, so the
two sides describe the same set of orders.

**Currency:** money. The result is expressed in the reporting currency.

**Excluded:** test transactions.

**Note:** for orders paid by instalments, the order value is the full order value,
not the instalment amount (§4.9).

---

### 2.7 Refund rate

**What is counted:** refunded amount in the window divided by captured GMV in the
same window, expressed as a percentage.

**Denominator:** captured GMV in the window, in the reporting currency.

**Date key:** each side is keyed on its own date — refunds on refund business
date, captures on capture business date. The two sides therefore do not describe
the same orders, and for a short window the rate can exceed 100% if a large
refund lands in a quiet period. This is expected.

**Currency:** both sides are converted to the reporting currency before dividing.
The ratio itself has no currency.

**Excluded:** test transactions; pending and failed refunds.

**Note:** this is a **value-based** rate. A count-based version ("what share of
orders were refunded") is a different number and is not what "refund rate" means
at Kestrel.

---

### 2.8 Payment success rate (order-level)

**This is what "success rate" means at Kestrel, unqualified.**

**What is counted:** the share of orders that were eventually paid.

**Numerator:** the number of distinct orders in the window that reached paid
status — that is, orders where **at least one** payment attempt was captured.

**Denominator:** the number of distinct orders in the window that had **at least
one payment attempt**. Orders where the customer never attempted payment are in
neither the numerator nor the denominator.

**Date key:** order business date.

**Currency:** none; this is a ratio.

**Excluded:** test orders and test attempts.

**Why order-level is the default:** customers retry. A customer whose first UPI
attempt fails and whose second succeeds has had a successful purchase, and the
business outcome is one paid order. Counting that customer as one success out of
two attempts describes the payment plumbing, not the shopping trip. When someone
asks "did our customers manage to pay us", the order-level number answers it.

**Broken down by bank or method,** the order is attributed to its final attempt
(§1.9). Per-bank order-level rates computed any other way will not reconcile to
the overall rate.

See §4.1 for the attempt-level metric and when to use it.

---

### 2.9 Payment success rate (attempt-level)

**What is counted:** the share of individual payment attempts that were captured.

**Numerator:** the number of payment attempts in the window that reached captured
status.

**Denominator:** the number of payment attempts in the window, of any outcome.

**Date key:** attempt business date.

**Currency:** none; this is a ratio.

**Excluded:** test attempts.

**When to use it:** this is the payment-operations number. It measures how well a
method, bank, or gateway is performing per try, and it is the right metric when
diagnosing a technical problem. It is **always lower** than the order-level rate
wherever customers retry, and the two must never be compared as though they were
the same measure.

---

### 2.10 Failure rate by reason

**What is counted:** for each failure reason, the share of payment attempts in
the window that failed with that reason.

**Numerator:** attempts that failed with the given reason.

**Denominator:** all payment attempts in the window, of any outcome — not just
failed ones. This means the rates across reasons sum to the overall attempt
failure rate, not to 100%.

**Date key:** attempt business date.

**Currency:** none; this is a ratio.

**Excluded:** test attempts.

---

### 2.11 EMI share

**What is counted:** the share of captured value that was paid by instalments.

**Numerator:** captured GMV in the window from orders paid by EMI.

**Denominator:** total captured GMV in the window.

**Date key:** capture business date.

**Currency:** both sides converted to the reporting currency before dividing.

**Excluded:** test transactions.

**Note:** the value counted is the **full order value**, not the monthly
instalment (§4.9). EMI is offered only in India and Malaysia, so an EMI share for
the UK or the UAE is legitimately zero rather than missing.

---

### 2.12 Accessory attach rate

**What is counted:** the share of phone purchases that also bought an accessory.

**Numerator:** paid orders in the window containing at least one phone line **and**
at least one accessory line.

**Denominator:** paid orders in the window containing at least one phone line.

Accessory-only orders are in neither the numerator nor the denominator: nothing
was attached to anything.

**Date key:** order business date.

**Currency:** none; this is a ratio.

**Excluded:** test orders; abandoned and cancelled orders.

---

### 2.13 Settlement lag

**Requires the finance capability.**

**What is counted:** the average number of days between money being captured from
the customer and the acquiring bank settling it to Kestrel.

**Denominator:** the number of captured payments in the window that have been
settled. Captures that have not settled yet are **excluded from the average** —
they have no lag to measure — and are reported separately as unsettled amount
(§2.14). Leaving them out means the average understates the problem when
settlement is delayed, so the two metrics must be read together.

**Date key:** the window is keyed on **settlement date**, not capture date. "What
was our settlement lag in August" means payments settled in August.

**Currency:** none; this is a count of days.

**Excluded:** test transactions.

---

### 2.14 Unsettled amount

**Requires the finance capability.**

**What is counted:** the total value of money captured from customers that the
acquiring bank has not yet settled to Kestrel as at the reporting date.

**Denominator:** not a ratio.

**Date key:** capture business date, for selecting which captures fall in the
window. Whether a capture is settled is assessed as at the reporting date.

**Currency:** money, converted at the daily rate for each amount's own capture
business date.

**Excluded:** test transactions.

**Note:** this is cash Kestrel has earned but not received. It grows naturally at
the end of a window — the most recent captures have not had time to settle — so
the number is only meaningful compared against the same point in an earlier
period, or against the normal settlement lag.

---

### 2.15 Duplicate capture count

**What is counted:** the number of captured payments that are duplicates of
another capture on the same order — the same money taken twice.

For a pair of duplicate captures the count is one: one capture is legitimate and
one is the duplicate. Three captures of the same amount count as two duplicates.

**Denominator:** not a ratio.

**Date key:** capture business date of the duplicate capture.

**Currency:** none; this is a count. The value involved is available separately.

**Excluded:** test transactions.

**Note:** duplicates are counted **once** in captured GMV (§2.3) so revenue is not
overstated, and they remain visible here so the operational problem is not
hidden. A store with duplicate captures usually also shows an unusual refund
pattern, because the duplicates are refunded once noticed.

---

## 3. What is not defined here

The following are **not** Kestrel metrics. Questions asking for them cannot be
answered from this glossary, and the honest answer is to say what is missing
rather than to substitute something close:

- Customer satisfaction, NPS, reviews, or any measure of sentiment.
- Profit, margin, cost of goods, or anything requiring cost data.
- Staff, headcount, footfall, or conversion from foot traffic.
- Stock on hand, availability, or supply-chain data.
- Anything about a future period: forecasts, predictions, or projections.
- Individual customer identity. Customer records exist in the operational
  database and are deliberately outside the semantic layer; no metric, dimension,
  or breakdown exposes them.

---

## 4. Definitional traps

Each of these is a question where two reasonable people compute different
numbers, both believing they are right. The rule Kestrel follows is stated for
each. These are the traps the evaluation is built around.

### 4.1 Attempts versus orders

A customer who fails once and succeeds on the retry produces two payment attempts
and one paid order. "Success rate" can therefore mean the share of orders that
got paid or the share of attempts that succeeded, and the two differ by a lot
wherever retries are common — which is everywhere UPI is used.

**Kestrel's rule:** unqualified "success rate" means **order-level** (§2.8).
Attempt-level is a separate, explicitly named metric (§2.9). An answer that gives
one must say which it gave.

### 4.2 Authorised versus captured

An authorisation reserves the customer's funds; a capture takes them. Treating
authorisations as revenue overstates it, because some are never captured.

**Kestrel's rule:** revenue counts **captured** money only (§2.3). Authorised and
not captured is not revenue and never appears in a revenue figure.

### 4.3 Partial refunds

A customer who returns one item from a three-item order is refunded part of the
order. Counting that as a fully refunded order overstates refunds; ignoring it
understates them.

**Kestrel's rule:** refunds count the **amount actually refunded** (§2.4), keyed
on the date the refund was processed. Refund rate is value-based, not
count-based (§2.7).

### 4.4 Multi-currency totals

Kestrel takes money in six currencies stored in minor units. Summing the raw
stored numbers across countries produces a figure that is not money in any
currency — and it looks entirely plausible.

**Kestrel's rule:** convert every amount to a single reporting currency at the
daily rate for that amount's own business date, then total (§1.3). The reporting
currency is chosen by the rule in §1.4 and is always disclosed.

### 4.5 Local time versus UTC

Every timestamp is stored in UTC, but a business day is a local thing. In India
the offset is five and a half hours: a UTC-day query for "yesterday" starts at
5:30 a.m. Chennai time, dropping the previous evening's trade and adding the
current morning's.

**Kestrel's rule:** day-based questions use the **showroom's local business
date** (§1.7), which is stored on every fact row. UTC timestamps are never used
to derive a business day.

### 4.6 Fiscal versus calendar quarter

Kestrel's fiscal year starts in April. "Q2" means July–September to a finance
analyst and April–June to anyone reading a calendar. "This quarter" and "last
quarter" carry the same ambiguity.

**Kestrel's rule:** a quarter or year reference that does not say which calendar
it means is **ambiguous and must be clarified**, unless the asker has a saved
preference. Guessing is not acceptable, because both readings are defensible and
the numbers differ materially. Explicit references — "the September quarter",
"FY2026 Q2", "calendar Q2" — are not ambiguous and are answered directly.

### 4.7 Capture versus settlement

Money captured from a customer arrives at Kestrel's bank days later. Revenue
questions and cash questions therefore key on different dates, and a settlement
question answered on capture dates is wrong even though every number in it is
real.

**Kestrel's rule:** settlement metrics key on **settlement date** (§2.13).
Revenue metrics key on **capture business date** (§2.3). Unsettled amount is the
bridge between them (§2.14).

### 4.8 Test transactions

Test orders and test payment attempts live in the same tables as real ones. They
are a small share of rows, which is exactly why they survive: they move a number
by a few percent, which looks like noise rather than a bug.

**Kestrel's rule:** test transactions are **excluded from every metric, always**,
by the test flag (§1.1). They are never excluded by matching on names or amounts,
because that both misses tests and removes real business.

### 4.9 EMI

An instalment order has a full order value and a monthly instalment amount. Using
the instalment where the order value belongs understates revenue by the tenure —
a twelve-month EMI order looks like one twelfth of its size.

**Kestrel's rule:** the value of an EMI order is the **full order value** (§2.11).
Instalment amounts are never used in a revenue or order-value metric.

### 4.10 Duplicate captures

A retry that succeeds twice takes the customer's money twice. Counting both
inflates revenue; hiding both conceals an operational fault.

**Kestrel's rule:** duplicate captures are counted **once** in captured GMV
(§2.3) and **surfaced separately** in duplicate capture count (§2.15). The refund
that usually follows is counted normally, on its own refund date.

---

## 5. Vocabulary: everyday words and what they mean here

People do not ask for `gmv_captured`. They ask what they took, what they made,
how they did. This table is the mapping. **If an everyday word in a question does
not appear here and does not obviously name a metric in §2, the question is
ambiguous and must be clarified** — it is not an invitation to guess which metric
was meant.

| What people say | What it means at Kestrel | Section |
|---|---|---|
| sales, sold, turnover *(as money)* | Captured GMV | §2.3 |
| sales, sold *(as things)*, units, volume | Units sold — **includes accessories** | §2.2 |
| collected, we collected, took, we took, brought in, made | Captured GMV — money captured from the customer, **not** money settled to the bank | §2.3 |
| received, landed, hit our account, cash in the bank | Settled money; see settlement lag and unsettled amount | §2.13, §2.14 |
| success rate, payment success, did payments work | Payment success rate, **order-level** | §2.8 |
| failures, declines, rejections, drops | Failed payment attempts, by reason | §2.10 |
| refunds, returns *(as money)* | Refunded amount, on the refund date | §2.4 |
| basket size, ticket size, average spend | Average order value | §2.6 |
| attach rate, accessories with phones | Accessory attach rate | §2.12 |
| EMI, instalments, easy payments, no-cost EMI | EMI share, on **full order value** | §2.11 |
| double charge, charged twice, duplicate | Duplicate capture count | §2.15 |
| yesterday | The showroom's local business date, one day back | §1.7 |
| last week | The most recent complete **Monday–Sunday** week | §1.6 |
| last 7 days | The seven days ending yesterday — **not** the same as last week | §1.6 |
| this month, last month | Calendar months, on business dates | §1.5 |

Words that deliberately do **not** appear in this table, because they have no
single meaning at Kestrel: *revenue*, *best*, *top*, *worst*, *performance*,
*growth*, *quarter* on its own. See §6.

---

## 6. Where Kestrel has a default, and where it must ask

Two kinds of imprecision look identical in a question and must be handled
differently. Getting this boundary wrong in either direction is a failure: a
system that clarifies everything is useless, and one that never clarifies is
confidently wrong.

### 6.1 Terms with an official default — answer, and disclose the default

These are ambiguous in the wider world but **settled at Kestrel**. Answer them
directly using the default, and state in the answer which reading was used.

| Term | Default | Section |
|---|---|---|
| "success rate", unqualified | Order-level, not attempt-level | §2.8, §4.1 |
| "refund rate" | Value-based, not count-based | §2.7 |
| "orders", unqualified | All statuses, not just paid | §2.1 |
| "collected", "took", "made" | Captured, not settled | §2.3, §4.2 |
| "units" | Includes accessories | §2.2 |
| per-bank / per-method order breakdowns | Attributed to the final attempt | §1.9 |
| any money figure spanning currencies | Converted per §1.4, currency disclosed | §1.3, §4.4 |
| any day-based window | Showroom-local business date | §1.7, §4.5 |
| every metric | Test transactions excluded | §1.1, §4.8 |

### 6.2 Terms that require clarification — ask, do not guess

For these, two definitions are **both common at Kestrel and differ materially**.
There is no default, deliberately. Picking one silently produces a number that is
defensible, plausible, and possibly not what was asked for.

| Term | The competing readings |
|---|---|
| "revenue" | Captured GMV (gross) or net revenue (after refunds) — §2.3 vs §2.5 |
| "best" / "top" / "worst" store, model, bank, with no metric named | By value, by units, by success rate, by refund rate — all reasonable, all different rankings |
| "quarter", "Q2", "this quarter", "last quarter", "year" with no calendar named | Fiscal (April start) or calendar — §1.5, §4.6 |
| "how are we doing", "performance", "growth" with no metric named | Any metric in §2 |

A saved preference resolves the calendar case for a given user; nothing resolves
the others except asking.
