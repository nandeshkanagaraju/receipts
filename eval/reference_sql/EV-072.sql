-- qid:      EV-072
-- value:    ratio
-- shape:    ranking
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   accessory attach rate (§2.12), by channel
-- scope:    country MY
-- currency: none
-- top_k:    2
-- rule:     numerator: paid orders with a PHONE line and an ACCESSORY line; denominator:
--           paid orders with a phone line (§2.12). A count of orders, not a split of
--           money, so §1.7a's handset attribution does not apply.
-- excludes: test orders (§1.1); abandoned and cancelled orders
with lines as (
    select o.order_id, o.channel,
           max(case when not p.is_accessory then 1 else 0 end) as has_phone,
           max(case when p.is_accessory then 1 else 0 end) as has_accessory
    from orders o
    join order_items i on i.order_id = o.order_id
    join products p on p.sku = i.sku
    join showrooms s on s.showroom_id = o.showroom_id
    where not o.is_test and o.status = 'paid' and s.country_code = 'MY'
      and o.business_date between date '2026-08-01' and date '2026-08-31'
    group by o.order_id, o.channel
)
select channel as key, cast(sum(has_accessory) * 1.0 / count(*) as decimal(38,12)) as value
from lines where has_phone = 1 group by channel order by value desc, key asc limit 2
