-- qid:      HO-032
-- value:    money_minor
-- shape:    ranking
-- window:   july_2026          -> snapshot as at 2026-07-31   (§2.14, NOT a flow)
-- metric:   unsettled amount (§2.14) by acquiring bank
-- scope:    all countries
-- currency: USD (§1.4 rule 1 -- the asker named it)
-- top_k:    10
-- rule:     THIS IS A SNAPSHOT, NOT A FLOW (§2.14). "At the end of July" means as at
--           31 July: payments captured ON OR BEFORE that date that had NOT settled by
--           it. It is NOT "captures during July that are still unsettled" -- two
--           different questions, two different numbers, and only the snapshot reading
--           is this metric.
--           There is NO LOWER BOUND. A payment captured four months earlier and still
--           unsettled is included; unsettled cash does not age out of the figure.
--           "Not settled by D" is evaluated at D: a capture settled in August was
--           unsettled on 31 July and counts here.
--           Each amount converts at the daily rate for ITS OWN CAPTURE business date
--           (§2.14) -- the rate on the day the money was taken, not the rate on D. This
--           is the same convention as captured GMV (§2.3), so the two reconcile:
--           unsettled amount is a subset of past captured GMV, valued identically.
--           Requires the finance capability (§2.14); the asker is global_finance.
--           The bank is the acquiring bank on the capture itself.
--           A bank with nothing outstanding is an exact zero, not a missing row
--           (docs/M2_NOTES.md §5).
-- excludes: test orders and test attempts (§1.1); duplicate captures (§4.10)
with fx as (
    select c.rate_date,
           c.currency,
           cast(c.usd_per_unit / r.usd_per_unit as decimal(38,12)) as to_reporting
    from fx_rates c
    join fx_rates r on r.rate_date = c.rate_date and r.currency = 'USD'
),
captures as (
    select a.attempt_id, a.order_id, a.amount_minor, a.currency, a.business_date,
           a.acquiring_bank,
           row_number() over (
               partition by a.order_id, a.amount_minor
               order by a.attempt_no, a.attempt_id
           ) as capture_rank
    from payment_attempts a
    where a.status = 'captured'
      and not a.is_test
),
settled_by_d as (
    select distinct si.attempt_id
    from settlement_items si
    join settlements st on st.settlement_id = si.settlement_id
    where st.settled_on <= date '2026-07-31'
),
spine as (
    select distinct acquiring_bank from payment_attempts where acquiring_bank is not null
),
valued as (
    select c.acquiring_bank, sum(c.amount_minor * fx.to_reporting) as amount
    from captures c
    join orders o on o.order_id = c.order_id
    join fx on fx.currency = c.currency and fx.rate_date = c.business_date
    left join settled_by_d sd on sd.attempt_id = c.attempt_id
    where c.capture_rank = 1
      and not o.is_test
      and c.business_date <= date '2026-07-31'
      and sd.attempt_id is null
    group by c.acquiring_bank
)
select sp.acquiring_bank as key,
       cast(round(coalesce(v.amount, 0)) as bigint) as value
from spine sp
left join valued v on v.acquiring_bank = sp.acquiring_bank
order by value desc, key asc
limit 10
