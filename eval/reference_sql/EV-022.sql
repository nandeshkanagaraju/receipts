-- qid:      EV-022
-- value:    ratio
-- shape:    scalar
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   accessory attach rate (§2.12)
-- scope:    city Madurai
-- currency: none
-- rule:     numerator: paid orders with at least one PHONE line AND at least one
--           ACCESSORY line; denominator: paid orders with at least one phone line (§2.12).
--           A count of orders, not a split of money, so §1.7a does not apply (§2.12).
-- excludes: test orders (§1.1); abandoned and cancelled orders
with lines as (
    select o.order_id,
           max(case when not p.is_accessory then 1 else 0 end) as has_phone,
           max(case when p.is_accessory then 1 else 0 end) as has_accessory
    from orders o
    join order_items i on i.order_id = o.order_id
    join products p on p.sku = i.sku
    join showrooms s on s.showroom_id = o.showroom_id
    join cities ci on ci.city_id = s.city_id
    where not o.is_test and o.status = 'paid' and ci.name = 'Madurai'
      and o.business_date between date '2026-08-01' and date '2026-08-31'
    group by o.order_id
)
select cast(sum(has_accessory) * 1.0 / count(*) as decimal(38,12)) as value
from lines where has_phone = 1
order by value
