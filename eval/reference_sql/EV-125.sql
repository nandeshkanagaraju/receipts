-- qid:      EV-125
-- value:    money_minor
-- shape:    scalar
-- window:   this_month_to_date -> 2026-09-01 .. 2026-09-09   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   captured GMV (§2.3)
-- scope:    region IN-TN (Tamil Nadu) -- the asker's own scope
-- currency: INR (§1.4 rule 1 -- "in rupees")
-- rule:     "this month so far" is month-to-date: 1-9 September. The reporting day, the
--           10th, is EXCLUDED -- it is not over, and a partial day understates the figure
--           (§1.6a, §1.8). The last loaded business date is 2026-09-09, so the window is
--           trimmed to it either way (§1.8).
--           "Our" resolves to the asker's scope, injected from auth context (D7).
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
      and a.business_date between date '2026-09-01' and date '2026-09-09'
)
select cast(round(sum(c.amount_minor * fx.to_reporting)) as bigint) as value
from captures c join fx on fx.currency = c.currency and fx.rate_date = c.business_date
where c.capture_rank = 1
