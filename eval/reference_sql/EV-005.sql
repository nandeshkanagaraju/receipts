-- qid:      EV-005
-- value:    ratio
-- shape:    ranking
-- window:   august_2026        -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   refund rate (§2.7), by country
-- scope:    all countries
-- currency: USD (§1.4 rule 2 -- global_finance reports in USD); both sides converted before dividing
-- top_k:    6
-- rule:     refund rate is VALUE-based, not count-based (§2.7 note): refunded amount
--           over captured GMV, not the share of orders refunded.
--           Each side keeps its OWN date key -- refunds on refund business date, captures
--           on capture business date (§2.7) -- so the two sides do not describe the same
--           orders, and for a short window the rate can exceed 100%.
--           Partial refunds count for the amount actually refunded (§4.3).
-- excludes: test transactions (§1.1); pending and failed refunds; duplicate captures
with fx as (
    select c.rate_date,
           c.currency,
           cast(c.usd_per_unit / r.usd_per_unit as decimal(38,12)) as to_reporting
    from fx_rates c
    join fx_rates r on r.rate_date = c.rate_date and r.currency = 'USD'
),
captures as (
    select a.order_id, a.amount_minor, a.currency, a.business_date, s.country_code,
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
      and 1 = 1
      and a.business_date between date '2026-08-01' and date '2026-08-31'
),
captured as (
    select c.country_code,
           sum(c.amount_minor * fx.to_reporting) as amount
    from captures c
    join fx on fx.currency = c.currency and fx.rate_date = c.business_date
    where c.capture_rank = 1
    group by c.country_code
),
refunded as (
    select s.country_code,
           sum(rf.amount_minor * fx.to_reporting) as amount
    from refunds rf
    join orders o on o.order_id = rf.order_id
    join showrooms s on s.showroom_id = o.showroom_id
    join fx on fx.currency = rf.currency and fx.rate_date = rf.business_date
    where not o.is_test
      and rf.status = 'processed'
      and rf.business_date between date '2026-08-01' and date '2026-08-31'
    group by s.country_code
)
select captured.country_code as key,
       cast(coalesce(refunded.amount, 0) / captured.amount as decimal(38,12)) as value
from captured
left join refunded on refunded.country_code = captured.country_code
order by value desc, key asc
limit 6
