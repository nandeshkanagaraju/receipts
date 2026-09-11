-- qid:      EV-129
-- value:    money_minor
-- shape:    compare
-- window:   this_month_to_date -> 2026-09-01 .. 2026-09-09   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   net revenue (§2.5)
-- scope:    country SG
-- currency: SGD (§1.4 rule 1 -- "in Singapore dollars")
-- rule:     EQUAL-LENGTH WINDOWS (§1.6a): the question says "the same days last month"
--           explicitly -- 1-9 September against 1-9 August, nine days each.
--           Net revenue is captured GMV minus refunds PROCESSED in the same window (§2.5),
--           each side converted at its own date before subtracting.
--           Both values are returned, keyed `current` and `comparison` (ADR-009).
-- excludes: test transactions (§1.1); pending and failed refunds; duplicate captures
with fx as (
    select c.rate_date,
           c.currency,
           cast(c.usd_per_unit / r.usd_per_unit as decimal(38,12)) as to_reporting
    from fx_rates c
    join fx_rates r on r.rate_date = c.rate_date and r.currency = 'SGD'
),
periods as (
    select date '2026-09-01' as lo, date '2026-09-09' as hi, 'current' as period
    union all
    select date '2026-08-01', date '2026-08-09', 'comparison'
),
captures as (
    select a.order_id, a.amount_minor, a.currency, a.business_date, p.period,
           row_number() over (
               partition by a.order_id, a.amount_minor
               order by a.attempt_no, a.attempt_id
           ) as capture_rank
    from payment_attempts a
    join orders o on o.order_id = a.order_id
    join showrooms s on s.showroom_id = o.showroom_id
    join periods p on a.business_date between p.lo and p.hi
    where a.status = 'captured' and not a.is_test and not o.is_test
      and s.country_code = 'SG'
),
captured as (
    select c.period, sum(c.amount_minor * fx.to_reporting) as amount
    from captures c join fx on fx.currency = c.currency and fx.rate_date = c.business_date
    where c.capture_rank = 1 group by c.period
),
refunded as (
    select p.period, sum(rf.amount_minor * fx.to_reporting) as amount
    from refunds rf
    join orders o on o.order_id = rf.order_id
    join showrooms s on s.showroom_id = o.showroom_id
    join periods p on rf.business_date between p.lo and p.hi
    join fx on fx.currency = rf.currency and fx.rate_date = rf.business_date
    where not o.is_test and rf.status = 'processed' and s.country_code = 'SG'
    group by p.period
)
select captured.period as key,
       cast(round(captured.amount - coalesce(refunded.amount, 0)) as bigint) as value
from captured left join refunded on refunded.period = captured.period
order by key asc
