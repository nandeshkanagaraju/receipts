-- qid:      EV-018
-- value:    ratio
-- shape:    scalar
-- window:   last_week          -> 2026-08-31 .. 2026-09-06   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   refund rate (§2.7)
-- scope:    region IN-TN (Tamil Nadu) -- the asker's own scope
-- currency: INR (§1.4 rule 2 -- rm_tamil_nadu reports in INR); both sides converted before dividing
-- rule:     refund rate is VALUE-based, not count-based (§2.7 note).
--           Each side keeps its own date key -- refunds on refund business date, captures
--           on capture business date (§2.7). Partial refunds count for the amount actually
--           refunded, not the value of the original order (§4.3).
--           "Our" resolves to the asker's scope, Tamil Nadu, injected from auth context
--           and never present in the question (D7).
-- excludes: test transactions (§1.1); pending and failed refunds; duplicate captures
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
),
captured as (
    select sum(c.amount_minor * fx.to_reporting) as amount
    from captures c join fx on fx.currency = c.currency and fx.rate_date = c.business_date
    where c.capture_rank = 1
),
refunded as (
    select coalesce(sum(rf.amount_minor * fx.to_reporting), 0) as amount
    from refunds rf
    join orders o on o.order_id = rf.order_id
    join showrooms s on s.showroom_id = o.showroom_id
    join fx on fx.currency = rf.currency and fx.rate_date = rf.business_date
    where not o.is_test and rf.status = 'processed' and s.region_id = 'IN-TN'
      and rf.business_date between date '2026-08-31' and date '2026-09-06'
)
select cast(refunded.amount / captured.amount as decimal(38,12)) as value
from refunded, captured
