-- qid:      EV-128
-- value:    ratio
-- shape:    compare
-- window:   this_month_to_date -> 2026-09-01 .. 2026-09-09   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   accessory attach rate (§2.12)
-- scope:    country GB
-- currency: none
-- rule:     EQUAL-LENGTH WINDOWS (§1.6a): 1-9 September against 1-9 August, nine days
--           each -- not the whole of August. The rule applies to a RATIO as well as to an
--           additive metric: a nine-day rate and a thirty-one-day rate are not comparable
--           because the day-of-week mix differs.
--           Numerator: paid orders with a phone line AND an accessory line; denominator:
--           paid orders with a phone line (§2.12). Keyed on ORDER business date.
--           Both values are returned, keyed `current` and `comparison` (ADR-009).
-- excludes: test orders (§1.1); abandoned and cancelled orders
with lines as (
    select o.order_id, o.business_date,
           max(case when not p.is_accessory then 1 else 0 end) as has_phone,
           max(case when p.is_accessory then 1 else 0 end) as has_accessory
    from orders o
    join order_items i on i.order_id = o.order_id
    join products p on p.sku = i.sku
    join showrooms s on s.showroom_id = o.showroom_id
    where not o.is_test and o.status = 'paid' and s.country_code = 'GB'
      and (o.business_date between date '2026-09-01' and date '2026-09-09'
        or o.business_date between date '2026-08-01' and date '2026-08-09')
    group by o.order_id, o.business_date
)
select case when business_date >= date '2026-09-01' then 'current' else 'comparison' end as key,
       cast(sum(has_accessory) * 1.0 / count(*) as decimal(38,12)) as value
from lines where has_phone = 1 group by key order by key asc
