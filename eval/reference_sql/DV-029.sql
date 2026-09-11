-- qid:      DV-029
-- value:    count
-- shape:    ranking
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   units sold (§2.2), restricted to handsets
-- scope:    all countries
-- currency: none
-- top_k:    10
-- rule:     "phone models" means HANDSETS ONLY and excludes accessories
--           (§2.2): "phone", "phone model", "handset" and "device" always mean
--           handsets, while "units" on its own counts cases and chargers too.
--           So this is the filtered version of units sold, not a different
--           metric.
--           Units counts LINES, so an accessory belongs to itself and is not
--           attributed to the handset it was bought with -- unlike order-level
--           money, which is attributed entirely to the handset (§1.7a). This is
--           the one place a product breakdown of units and of money describe
--           different things, and the difference is intended.
-- excludes: test orders (§1.1); abandoned and cancelled orders (§2.2)
select p.model_name as key,
       sum(i.qty) as value
from order_items i
join orders o on o.order_id = i.order_id
join products p on p.sku = i.sku
where not o.is_test
  and o.status = 'paid'
  and not p.is_accessory
  and o.business_date between date '2026-08-01' and date '2026-08-31'
group by p.model_name
order by value desc, key asc
limit 10
