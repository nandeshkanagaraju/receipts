-- qid:      EV-016
-- value:    ratio
-- shape:    ranking
-- window:   july_2026          -> 2026-07-01 .. 2026-07-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   accessory attach rate (§2.12), by country
-- scope:    all countries
-- currency: none
-- top_k:    6
-- rule:     numerator: paid orders with at least one PHONE line AND at least one
--           ACCESSORY line. Denominator: paid orders with at least one phone line (§2.12).
--           This is a count of ORDERS, not a split of money, so the §1.7a
--           handset-attribution rule does not apply. Keyed on ORDER business date.
-- excludes: test orders (§1.1); abandoned and cancelled orders (§2.12)
with lines as (
    select o.order_id, s.country_code,
           max(case when not p.is_accessory then 1 else 0 end) as has_phone,
           max(case when p.is_accessory then 1 else 0 end) as has_accessory
    from orders o
    join order_items i on i.order_id = o.order_id
    join products p on p.sku = i.sku
    join showrooms s on s.showroom_id = o.showroom_id
    where not o.is_test and o.status = 'paid'
      and o.business_date between date '2026-07-01' and date '2026-07-31'
    group by o.order_id, s.country_code
)
select country_code as key,
       cast(sum(has_accessory) * 1.0 / count(*) as decimal(38,12)) as value
from lines where has_phone = 1 group by country_code order by value desc, key asc limit 6
