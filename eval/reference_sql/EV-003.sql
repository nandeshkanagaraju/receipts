-- qid:      EV-003
-- value:    money_minor
-- shape:    ranking
-- window:   yesterday          -> 2026-09-09 .. 2026-09-09   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   captured GMV (§2.3), by city
-- scope:    region IN-TN (Tamil Nadu)
-- currency: INR (§1.4 rule 1 -- "in rupees")
-- top_k:    10
-- rule:     "yesterday" is the SHOWROOM'S own local business date (§1.7), never a UTC
--           day: in India the offset is five and a half hours, so a UTC-day query starts
--           at 5:30 a.m. Chennai time, drops the previous evening's trade and adds the
--           current morning's (§4.5). The local date is stored on every fact row.
-- excludes: test transactions (§1.1); duplicate captures
with fx as (
    select c.rate_date,
           c.currency,
           cast(c.usd_per_unit / r.usd_per_unit as decimal(38,12)) as to_reporting
    from fx_rates c
    join fx_rates r on r.rate_date = c.rate_date and r.currency = 'INR'
),
captures as (
    select a.order_id, a.amount_minor, a.currency, a.business_date, s.city_id,
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
      and a.business_date between date '2026-09-09' and date '2026-09-09'
)
select ci.name as key,
       cast(round(sum(c.amount_minor * fx.to_reporting)) as bigint) as value
from captures c
join fx on fx.currency = c.currency and fx.rate_date = c.business_date
join cities ci on ci.city_id = c.city_id
where c.capture_rank = 1
group by key
order by value desc, key asc
limit 10
