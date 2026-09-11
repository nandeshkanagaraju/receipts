-- qid:      EV-062
-- value:    money_minor
-- shape:    scalar
-- window:   yesterday          -> 2026-09-09 .. 2026-09-09   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   captured GMV (§2.3)
-- scope:    city Chennai
-- currency: INR (§1.4 rule 1 -- "in rupees")
-- rule:     "yesterday" is the showroom's local business date (§1.7). In India the UTC
--           offset is five and a half hours, so a UTC-day query would start at 5:30 a.m.
--           Chennai time, drop the previous evening's trade and add the current morning's
--           (§4.5). The local date is stored on the row; no timestamp arithmetic is used.
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
    join cities ci on ci.city_id = s.city_id
    where a.status = 'captured'
      and not a.is_test
      and not o.is_test
      and ci.name = 'Chennai'
      and a.business_date between date '2026-09-09' and date '2026-09-09'
)
select cast(round(sum(c.amount_minor * fx.to_reporting)) as bigint) as value
from captures c join fx on fx.currency = c.currency and fx.rate_date = c.business_date
where c.capture_rank = 1
