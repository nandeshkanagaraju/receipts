-- qid:      EV-026
-- value:    ratio
-- shape:    ranking
-- window:   last_week          -> 2026-08-31 .. 2026-09-06   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   payment success rate, order-level (§2.8), by city
-- scope:    region IN-TN (Tamil Nadu), UPI attempts only
-- currency: none
-- top_k:    10
-- rule:     "tried" attribution (§1.9): denominator is orders that ATTEMPTED UPI,
--           numerator those with a CAPTURED UPI attempt. The breakdown here is
--           geographical, so the denominators do NOT overlap between cities -- an order
--           belongs to one showroom -- but they are still the UPI-tried subset, not all
--           orders, so these rates are not the overall order-level rate per city.
--           Keyed on ORDER business date (§2.8).
-- excludes: test orders and test attempts (§1.1)
with scope as (
    select o.order_id, ci.name as city
    from orders o
    join showrooms s on s.showroom_id = o.showroom_id
    join cities ci on ci.city_id = s.city_id
    where not o.is_test and s.region_id = 'IN-TN'
      and o.business_date between date '2026-08-31' and date '2026-09-06'
),
tried as (
    select sc.city, a.order_id,
           max(case when a.status = 'captured' then 1 else 0 end) as succeeded
    from payment_attempts a
    join scope sc on sc.order_id = a.order_id
    where not a.is_test and a.method = 'upi'
    group by sc.city, a.order_id
)
select city as key, cast(sum(succeeded) * 1.0 / count(*) as decimal(38,12)) as value
from tried group by city order by value desc, key asc limit 10
