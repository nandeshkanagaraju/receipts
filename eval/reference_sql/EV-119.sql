-- qid:      EV-119
-- value:    ratio
-- shape:    compare
-- window:   this_month_to_date -> 2026-09-01 .. 2026-09-09   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   refund rate (§2.7), by country
-- scope:    all countries
-- currency: USD (§1.4 rule 2 -- global_finance reports in USD); both sides converted before dividing
-- top_k:    6
-- rule:     EQUAL-LENGTH WINDOWS (§1.6a): 1-9 September against 1-9 August, nine days
--           each -- not the whole of August.
--           Refund rate is VALUE-based (§2.7); each side keeps its own date key, so within
--           a period the refunds and the captures are not the same orders.
--           Keys are `<country>|current` and `<country>|comparison` so both periods must
--           be present per country (ADR-009).
-- excludes: test transactions (§1.1); pending and failed refunds; duplicate captures
with fx as (
    select c.rate_date,
           c.currency,
           cast(c.usd_per_unit / r.usd_per_unit as decimal(38,12)) as to_reporting
    from fx_rates c
    join fx_rates r on r.rate_date = c.rate_date and r.currency = 'USD'
),
periods as (
    select date '2026-09-01' as lo, date '2026-09-09' as hi, 'current' as period
    union all
    select date '2026-08-01', date '2026-08-09', 'comparison'
),
captures as (
    select a.order_id, a.amount_minor, a.currency, a.business_date, p.period, s.country_code,
           row_number() over (
               partition by a.order_id, a.amount_minor
               order by a.attempt_no, a.attempt_id
           ) as capture_rank
    from payment_attempts a
    join orders o on o.order_id = a.order_id
    join showrooms s on s.showroom_id = o.showroom_id
    join periods p on a.business_date between p.lo and p.hi
    where a.status = 'captured' and not a.is_test and not o.is_test
),
captured as (
    select c.country_code, c.period, sum(c.amount_minor * fx.to_reporting) as amount
    from captures c join fx on fx.currency = c.currency and fx.rate_date = c.business_date
    where c.capture_rank = 1 group by c.country_code, c.period
),
refunded as (
    select s.country_code, p.period, sum(rf.amount_minor * fx.to_reporting) as amount
    from refunds rf
    join orders o on o.order_id = rf.order_id
    join showrooms s on s.showroom_id = o.showroom_id
    join periods p on rf.business_date between p.lo and p.hi
    join fx on fx.currency = rf.currency and fx.rate_date = rf.business_date
    where not o.is_test and rf.status = 'processed'
    group by s.country_code, p.period
)
select captured.country_code || '|' || captured.period as key,
       cast(coalesce(refunded.amount, 0) / captured.amount as decimal(38,12)) as value
from captured
left join refunded on refunded.country_code = captured.country_code
                  and refunded.period = captured.period
order by key asc
