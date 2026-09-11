-- qid:      EV-112
-- value:    money_minor
-- shape:    ranking
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   captured GMV (§2.3), by showroom
-- scope:    city Coimbatore
-- currency: INR (§1.4 rule 1 -- "in rupees")
-- top_k:    10
-- rule:     captured money only (§4.2); duplicates counted once (§4.10).
--           The breakdown is by showroom within one city, so the rows partition the city's
--           captured GMV and do sum to it -- unlike a per-method success rate (§1.9).
-- excludes: test transactions (§1.1); duplicate captures
with fx as (
    select c.rate_date,
           c.currency,
           cast(c.usd_per_unit / r.usd_per_unit as decimal(38,12)) as to_reporting
    from fx_rates c
    join fx_rates r on r.rate_date = c.rate_date and r.currency = 'INR'
),
captures as (
    select a.order_id, a.amount_minor, a.currency, a.business_date, o.showroom_id,
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
      and ci.name = 'Coimbatore'
      and a.business_date between date '2026-08-01' and date '2026-08-31'
)
select sh.name as key,
       cast(round(sum(c.amount_minor * fx.to_reporting)) as bigint) as value
from captures c
join fx on fx.currency = c.currency and fx.rate_date = c.business_date
join showrooms sh on sh.showroom_id = c.showroom_id
where c.capture_rank = 1 group by sh.name order by value desc, key asc limit 10
