-- qid:      EV-126
-- value:    count
-- shape:    ranking
-- window:   july_2026          -> 2026-07-01 .. 2026-07-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   units sold (§2.2), by phone model
-- scope:    country GB
-- currency: none
-- top_k:    10
-- rule:     "phone models" means HANDSETS ONLY and excludes accessories (§2.2):
--           "phone", "handset" and "device" always mean handsets, while "units" on its own
--           counts cases and chargers too. This is the filtered version of units sold, not
--           a separate metric.
--           Units counts LINES, so an accessory belongs to itself rather than to the
--           handset it was bought with -- unlike order-level money (§1.7a).
-- excludes: test orders (§1.1); abandoned and cancelled orders
select p.model_name as key, sum(i.qty) as value
from order_items i
join orders o on o.order_id = i.order_id
join products p on p.sku = i.sku
join showrooms s on s.showroom_id = o.showroom_id
where not o.is_test and o.status = 'paid' and not p.is_accessory
  and s.country_code = 'GB'
  and o.business_date between date '2026-07-01' and date '2026-07-31'
group by p.model_name order by value desc, key asc limit 10
