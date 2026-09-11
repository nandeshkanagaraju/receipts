-- qid:      EV-064
-- value:    ratio
-- shape:    compare
-- window:   last_week          -> 2026-08-31 .. 2026-09-06   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   refund rate (§2.7)
-- scope:    country GB
-- currency: GBP (§1.4 rule 2 -- store_ops_uk reports in GBP); both sides converted before dividing
-- rule:     two COMPLETE Monday-Sunday weeks, equal length (§1.6, §1.6a):
--           2026-08-31..2026-09-06 against 2026-08-24..2026-08-30.
--           Refund rate is VALUE-based (§2.7); each side keeps its own date key, so the
--           refunds and the captures in a week are not the same orders. Partial refunds
--           count for the amount actually refunded (§4.3).
--           Both values are returned, keyed `current` and `comparison` (ADR-009).
-- excludes: test transactions (§1.1); pending and failed refunds; duplicate captures
with fx as (
    select c.rate_date,
           c.currency,
           cast(c.usd_per_unit / r.usd_per_unit as decimal(38,12)) as to_reporting
    from fx_rates c
    join fx_rates r on r.rate_date = c.rate_date and r.currency = 'GBP'
),
periods as (
    select date '2026-08-31' as lo, date '2026-09-06' as hi, 'current' as period
    union all
    select date '2026-08-24', date '2026-08-30', 'comparison'
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
      and s.country_code = 'GB'
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
    where not o.is_test and rf.status = 'processed' and s.country_code = 'GB'
    group by p.period
)
select captured.period as key,
       cast(coalesce(refunded.amount, 0) / captured.amount as decimal(38,12)) as value
from captured left join refunded on refunded.period = captured.period
order by key asc
