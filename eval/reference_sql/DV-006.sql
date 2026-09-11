-- qid:      DV-006
-- value:    ratio
-- shape:    scalar
-- window:   this_month_to_date -> 2026-09-01 .. 2026-09-09   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   refund rate (§2.7)
-- scope:    region IN-TN (Tamil Nadu)
-- currency: INR for both sides before dividing (§1.4 rule 2, rm_tamil_nadu)
-- rule:     refund rate is VALUE-based, not count-based (§2.7 note): refunded
--           amount over captured GMV, not the share of orders refunded. Each
--           side is keyed on its own date -- refunds on refund business date,
--           captures on capture business date (§1.2) -- so the two sides do not
--           describe the same orders. Partial refunds count for the amount
--           actually refunded (§4.3).
--           "This month" is month-to-date, 1-9 September, not all of September.
-- excludes: test transactions (§1.1); pending and failed refunds (§2.4)
with fx as (
    select c.rate_date,
           c.currency,
           cast(c.usd_per_unit / r.usd_per_unit as decimal(38,12)) as to_reporting
    from fx_rates c
    join fx_rates r on r.rate_date = c.rate_date and r.currency = 'INR'
),
refunded as (
    select sum(rf.amount_minor * fx.to_reporting) as amount
    from refunds rf
    join orders o on o.order_id = rf.order_id
    join showrooms s on s.showroom_id = o.showroom_id
    join fx on fx.currency = rf.currency and fx.rate_date = rf.business_date
    where not o.is_test
      and rf.status = 'processed'
      and s.region_id = 'IN-TN'
      and rf.business_date between date '2026-09-01' and date '2026-09-09'
),
captures as (
    select a.amount_minor, a.currency, a.business_date,
           row_number() over (
               partition by a.order_id, a.amount_minor
               order by a.attempt_no, a.attempt_id
           ) as capture_rank
    from payment_attempts a
    join orders o on o.order_id = a.order_id
    join showrooms s on s.showroom_id = o.showroom_id
    where a.status = 'captured'
      and not a.is_test
      and s.region_id = 'IN-TN'
      and a.business_date between date '2026-09-01' and date '2026-09-09'
),
captured as (
    select sum(c.amount_minor * fx.to_reporting) as amount
    from captures c
    join fx on fx.currency = c.currency and fx.rate_date = c.business_date
    where c.capture_rank = 1
)
select cast(refunded.amount / captured.amount as decimal(38,12)) as value
from refunded, captured
