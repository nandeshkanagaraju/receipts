-- qid:      DV-025
-- value:    ratio
-- shape:    ranking
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   EMI share (§2.11), by city
-- scope:    region IN-TN (Tamil Nadu)
-- currency: INR for both sides before dividing (§1.4 rule 2, rm_tamil_nadu)
-- top_k:    5
-- rule:     share of captured value paid by instalments, per city. The value is
--           the full order value, never the instalment (§4.9). Value metrics
--           broken down by method follow the money (§1.9), so a capture belongs
--           to its own attempt's method.
-- excludes: test transactions (§1.1); failed attempts; duplicate captures
with fx as (
    select c.rate_date,
           c.currency,
           cast(c.usd_per_unit / r.usd_per_unit as decimal(38,12)) as to_reporting
    from fx_rates c
    join fx_rates r on r.rate_date = c.rate_date and r.currency = 'INR'
),
captures as (
    select ci.name as city, a.method, a.amount_minor, a.currency, a.business_date,
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
      and s.region_id = 'IN-TN'
      and a.business_date between date '2026-08-01' and date '2026-08-31'
)
select c.city as key,
       cast(
           sum(case when c.method = 'emi' then c.amount_minor * fx.to_reporting else 0 end)
           / sum(c.amount_minor * fx.to_reporting)
       as decimal(38,12)) as value
from captures c
join fx on fx.currency = c.currency and fx.rate_date = c.business_date
where c.capture_rank = 1
group by c.city
order by value desc, key asc
limit 5
