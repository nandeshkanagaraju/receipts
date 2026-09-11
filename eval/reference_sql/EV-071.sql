-- qid:      EV-071
-- value:    money_minor
-- shape:    scalar
-- window:   last_week          -> 2026-08-31 .. 2026-09-06   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   average order value (§2.6)
-- scope:    region IN-TN (Tamil Nadu) -- the asker's own scope
-- currency: INR (§1.4 rule 2 -- rm_tamil_nadu reports in INR)
-- rule:     captured GMV over distinct PAID orders, both keyed on capture business date
--           so the two sides describe the same order set (§2.6). Abandoned and cancelled
--           orders are not in the denominator.
--           "Last week" is the most recent complete Monday-Sunday week (§1.6).
-- excludes: test transactions (§1.1); duplicate captures
with fx as (
    select c.rate_date,
           c.currency,
           cast(c.usd_per_unit / r.usd_per_unit as decimal(38,12)) as to_reporting
    from fx_rates c
    join fx_rates r on r.rate_date = c.rate_date and r.currency = 'INR'
),
captures as (
    select a.order_id, a.amount_minor, a.currency, a.business_date,
           row_number() over (
               partition by a.order_id, a.amount_minor
               order by a.attempt_no, a.attempt_id
           ) as capture_rank
    from payment_attempts a
    join orders o on o.order_id = a.order_id
    join showrooms s on s.showroom_id = o.showroom_id
    where a.status = 'captured'
      and not a.is_test
      and not o.is_test
      and s.region_id = 'IN-TN'
      and a.business_date between date '2026-08-31' and date '2026-09-06'
)
select cast(round(
           sum(c.amount_minor * fx.to_reporting) / count(distinct c.order_id)
       ) as bigint) as value
from captures c join fx on fx.currency = c.currency and fx.rate_date = c.business_date
where c.capture_rank = 1
