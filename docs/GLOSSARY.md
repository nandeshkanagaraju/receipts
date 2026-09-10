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

### 1.6a Rolling and comparison windows

Three phrasings that look interchangeable and are not. All examples are against
the reporting date **2026-09-10** (a Thursday), whose last loaded business date
is **2026-09-09**.

| Phrase | Window | Note |
|---|---|---|
| "last 7 days" | `2026-09-03` … `2026-09-09` | Seven days ending **yesterday**. The reporting day itself is **excluded**: it is not over, and including a partial day understates every daily figure |
| "last week" | `2026-08-31` … `2026-09-06` | The most recent **complete** Monday–Sunday week |
| "last N weeks" | `2026-07-13` … `2026-09-06` for N=8 | N **complete** Monday–Sunday weeks. The current partial week is **excluded**, not counted as one of the N |

**"This month versus last month" compares equal-length windows.** "This month" is
month-to-date — `2026-09-01` … `2026-09-09`, nine days — and the comparison is the
**same days of the previous month**, `2026-08-01` … `2026-08-09`, also nine days.
It is *not* the whole of August.

Comparing nine days against thirty-one would show a collapse in every additive
metric, every month, purely as an artefact of the calendar. Any comparison window
is the same length as the window it is compared against (SDD §9.1 rule 5). The
same applies to "versus the same month last year": nine days of September 2026
against `2025-09-01` … `2025-09-09`.

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

### 1.7a Attributing an order to a product

An order carries one handset and may carry accessories alongside it. Breaking
**order-level money** down by a product dimension — model, storage size, colour —
therefore needs a rule, because the order's money is one number and its lines are
several.

**Kestrel's rule:** captured GMV, refunded amount and net revenue broken down by
a product dimension are attributed **entirely to the order's handset**. The whole
order value sits against that handset's model, storage and colour; the accessory
lines contribute nothing to the split.

So "captured GMV by model" reads as *the value of orders whose handset was that
model* — including the case and charger bought with it. It is not an allocation
of the order across its lines, and the parts do not need apportioning, because
every order has exactly one handset.

**Units sold is not affected** (§2.2). Units counts lines, so an accessory is its
own unit and belongs to itself, not to the handset it was bought with. This is the
one place where a product breakdown of units and a product breakdown of money
describe different things, and the difference is intended: "which model sold the
most units" and "which model brought in the most money" are different questions.

**Attach rate is not affected either** (§2.12): it is a count of orders, not a
split of money.

### 1.8 Freshness

Data covers business dates from 1 March 2025 to 9 September 2026 inclusive. The
reporting date is 10 September 2026. A window that runs past the last loaded
business date is trimmed to it, and the answer says so.

### 1.9 Attributing an order to a payment method, bank, or network

An order can carry payment attempts on different methods and different banks: a
customer whose card is declined may retry with UPI, or switch to a second card.
Any **order-level** metric broken down by method, card network, or issuing bank
therefore needs a rule for which one the order belongs to. There are two rules,
for two different kinds of metric, and using the wrong one is a serious error.

#### Success rates use "tried" attribution

For **order-level success rates broken down by method, issuing bank, or card
network** (§2.8):

- **Denominator:** orders with at least one non-test attempt **on that method,
  bank, or network**.
- **Numerator:** those same orders that had a **captured** attempt on **that same
  method, bank, or network**.

An order that tried UPI, failed, and then paid by card appears in **both** UPI's
denominator and card's denominator. It counts as a failure for UPI and a success
for card. That is the correct reading: UPI did fail that customer, and card did
succeed.

**Why not attribute the order to its final attempt.** It inverts the metric.
Under final-attempt attribution the order above leaves UPI's denominator
entirely, because the customer ended on card. Every UPI failure that the customer
recovers from on another method disappears from UPI's figures — so **UPI's
success rate rises precisely when UPI is failing**, and the worse the outage, the
better the number looks, as long as customers switch. A metric that improves
during the incident it is supposed to detect is worse than no metric.

#### Per-method rates do not sum to the overall rate

This follows directly, and is expected rather than a defect:

- The denominators **overlap**. One order can sit in several of them.
- Their union is **larger** than the number of orders, because retry-switchers are
  counted once per method they tried.
- So the per-method denominators do not partition the orders, and the per-method
  rates cannot be combined — by averaging, by weighting, or by any other means —
  to reproduce the overall order-level rate in §2.8.

Any answer showing a per-method or per-bank breakdown alongside an overall figure
must say so. The two are different populations, and a reader who assumes the
parts add up to the whole will conclude something false.

#### Value and count metrics follow the money

For metrics that count **value or volume** rather than success — captured GMV,
net revenue, EMI share, average order value, refunded amount — a per-method or
per-bank breakdown attributes each amount to the attempt that actually carried
it: the **capture** for captured money, the refund's own attempt for refunds.
No order-level attribution rule is needed, because the money itself is already
attached to one attempt. These breakdowns **do** partition the total and **do**
sum to it.

#### Attempt-level metrics need no attribution rule at all

Every attempt already carries its own method, network, and bank (§2.9, §2.10).
This is a second reason attempt-level and order-level breakdowns differ, on top
of retries.

---

## 2. Metric definitions

### 2.1 Orders count

**What is counted:** the number of orders created in the window. **All three
order statuses count**, with no exception:

| Status | Meaning | Counted? |
|---|---|---|
| `paid` | At least one payment attempt was captured | Yes |
| `abandoned` | The customer left without completing payment | Yes |
| `cancelled` | The order was cancelled after being placed | Yes |

So "how many orders did we take" counts all three. "How many orders did we get
paid for" is a **different** question and a different number — that is the count
of `paid` orders, which appears as the denominator of average order value (§2.6)
and inside the numerator of order-level success rate (§2.8). Neither of those is
`orders_count`.

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

**"Phone", "phone model", "handset" and "device" always mean handsets only** and
exclude accessories. "Units" is the opposite: it counts everything. So "top phone
models by units sold" means handset SKUs ranked by their unit count, while "units
sold" on its own includes the cases and chargers too.

**Accessories are included in units.** A "unit" at Kestrel is any item on an order line —
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

### 2.4a Refund age

**What is counted:** how long a refund has been outstanding, in whole days.

**Definition:** the reporting date minus the refund's **creation** business date.
A refund created on 2026-09-01, read on the reporting date 2026-09-10, is **9
days** old.

Note this keys on the date the refund was *created*, not the date it was
processed. An unprocessed refund has no processed date, and age is precisely the
question one asks about refunds that have not completed.

**Denominator:** not a ratio.

**Currency:** none; this is a count of days.

**Excluded:** test transactions.

**Where it is used:** listing refunds still pending at the payment gateway
(§6.3). Age is a property of each refund record, not an aggregate.

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

**Broken down by bank, method, or network,** this metric uses **"tried"
attribution** (§1.9): the denominator is orders that attempted on that
method/bank/network, and the numerator is those that succeeded on it. Per-method
rates therefore do **not** sum or reconcile to this overall figure, because their
denominators overlap. §1.9 explains why final-attempt attribution would make a
method's rate improve when the method fails.

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

**Denominator: all payment attempts in the window, of any outcome** — captured,
authorised, and failed alike. It is **not** the number of failed attempts.

The consequence is worth stating plainly, because it is the thing people get
wrong: the rates across reasons **sum to the overall attempt failure rate, not to
100%**. If 8% of attempts failed, the per-reason rates sum to 8%. A set of
per-reason figures that sums to 100% has been computed against the wrong
denominator — it is the *share of failures* by reason, which is a different and
undefined quantity at Kestrel.

A plain **count** of failures by reason is also not this metric. Counts are
legitimate but undefined here; a question asking for them is answerable from the
tables without being covered by the glossary.

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

Accessory-only orders would be in neither the numerator nor the denominator —
nothing was attached to anything. In Kestrel's data this case does not arise:
every order carries exactly one handset (§1.7a). The rule is stated so the metric
remains well defined if that ever changes.

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

**Date key: this is a snapshot, not a flow.** It is evaluated **as at the end of
the window**, call that date D:

- **Included:** payments captured **on or before D** that had **not settled by
  D**.
- There is no lower bound. A payment captured four months before D and still
  unsettled is included; unsettled cash does not age out of the figure.
- Asking for "unsettled amount in August" means **as at 31 August**, not
  "captures during August that are still unsettled".

Two different questions therefore produce two different numbers, and only the
snapshot reading is this metric.

**Currency:** money. Each amount is converted at the daily rate for **its own
capture business date** — the rate on the day the money was taken, not the rate
on D. This is the same convention as captured GMV (§2.3), so the two reconcile:
unsettled amount is a subset of past captured GMV, valued identically.

**Excluded:** test transactions.

**Note:** this is cash Kestrel has earned but not received. It is always non-zero
and always includes the last few days of captures, which simply have not had time
to settle. The number is meaningful only against the same point in an earlier
period, or read together with settlement lag (§2.13).

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

## 5. Vocabulary: what people actually say

People do not ask for `gmv_captured`. They ask what they took, how many they
took, how they did.

**This table maps phrases, not words**, because the same verb means different
things depending on its object. "How much did we take" is money; "how many orders
did we take" is a count; "how long did settlement take" is neither. A word-level
map would collapse all three.

**If a phrase in a question does not match a row here and does not obviously name
a metric in §2, the question is ambiguous and must be clarified** — it is not an
invitation to guess.

### 5.1 Money

| What people say | What it means | Section |
|---|---|---|
| how much did we **take** / **collect** / **make** / **bring in** / **do** | Captured GMV — money captured from the customer | §2.3 |
| what were our **sales** / **turnover** *(as an amount)* | Captured GMV | §2.3 |
| how much did we **receive** / has **landed** / **hit our account** / is **in the bank** | Settled money — a different date and a different number | §2.13, §2.14 |
| how much are we **owed** / **waiting on** / **yet to receive** | Unsettled amount, as at the end of the window | §2.14 |
| how much did we **refund** / **give back** / **pay back** | Refunded amount, on the refund date | §2.4 |
| what is our **average order** / **basket size** / **ticket size** / **average spend** | Average order value | §2.6 |
| what did we **make after refunds** / **net of returns** | Net revenue | §2.5 |

### 5.2 Counts and volumes

| What people say | What it means | Section |
|---|---|---|
| how many **orders** did we **take** / **get** / **do** / **have** | Orders count — **all statuses**, paid and abandoned and cancelled | §2.1 |
| how many **orders did we get paid for** / **went through** | Count of `paid` orders — **not** orders count | §2.1, §2.6 |
| how many did we **sell** / how many **units** / what **volume** | Units sold — **includes accessories** | §2.2 |
| how many **phones** / **handsets** / **devices** did we sell | Units sold, **handsets only**, accessories excluded | §2.2 |
| how many **double charges** / **charged twice** / **duplicates** | Duplicate capture count | §2.15 |
| how many **different banks** / **how many networks** we saw | Not a Kestrel metric — countable from the tables, undefined here | — |

### 5.3 Payments

| What people say | What it means | Section |
|---|---|---|
| what is our **success rate** / did **payments work** / are payments **going through** | Payment success rate, **order-level** | §2.8 |
| success rate **for UPI** / **for card** / **for a bank** | Order-level success with **"tried" attribution**; does not sum to the overall rate | §1.9, §2.8 |
| **per-try** / **per-attempt** success | Payment success rate, attempt-level | §2.9 |
| what is **failing** / why are payments **declining** / **failure reasons** | Failure rate by reason — denominator is **all attempts** | §2.10 |
| how much on **EMI** / **instalments** / **easy payments** | EMI share, on **full order value** | §2.11 |
| how long does **settlement take** / what is our **settlement lag** | Settlement lag, keyed on settlement date | §2.13 |
| are people **buying accessories with** phones / **attach rate** | Accessory attach rate | §2.12 |

### 5.3a "EMI orders", "card-paid orders", and other method-qualified orders

A phrase like **"EMI orders"**, **"card-paid orders"** or **"orders paid by UPI"**
means orders whose **captured** attempt used that method — the method the money
actually came in on.

**This is deliberately not the "tried" rule.** §1.9 attributes an order to every
method it *attempted*, and that rule applies **only to success rates**, where the
question is whether a method worked. Everywhere else — filtering a set of orders,
splitting value by method, averaging order value for a method — the order belongs
to the method that paid.

The two rules answer different questions and would give different answers on the
same order:

| An order that tried UPI, failed, then paid by card | |
|---|---|
| UPI success rate (§1.9, tried) | Counts as a **UPI failure** and a card success |
| "card-paid orders" (this rule) | Is a **card order**. It is not a UPI order |

An order that was never captured has no paying method and is in no method-
qualified set at all.

### 5.4 Time

| What people say | What it means | Section |
|---|---|---|
| **yesterday** | The showroom's local business date, one day back | §1.7 |
| **last week** | The most recent complete **Monday–Sunday** week | §1.6 |
| **last 7 days** | The seven days ending yesterday — **not** the same as last week | §1.6 |
| **this month**, **last month** | Calendar months, on business dates | §1.5 |
| **so far this year** | From 1 January, unless the asker says fiscal | §1.5 |

### 5.5 Phrases that deliberately have no entry

*revenue* · *best* · *top* · *worst* · *performance* · *how are we doing* ·
*growth* · *quarter* on its own. Each has more than one defensible reading at
Kestrel. See §6.

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
| "sales", unqualified | **Captured GMV** — money, not units. Disclose the reading and offer units sold as the sibling, since "how much did we sell" and "how many did we sell" are both ordinary meanings | §2.3, §2.2 |
| "refunds" as a noun | **Refunded amount** — the value refunded, on the refund date | §2.4 |
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

### 6.3 One exception: "refunds" in a gateway question

"Refunds" defaults to the refunded-amount metric (§6.1), but in a **live gateway
question** it means the individual refund **records** — "which refunds are still
pending", "how old are the pending refunds". These ask for a list of rows, not a
total, and answering with a single amount would be wrong.

The distinguishing signal is the gateway: a question about what is *pending at
the payment gateway* is asking about records. A question about how much was
refunded is asking for the metric.
