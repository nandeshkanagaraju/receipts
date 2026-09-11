-- qid:      EV-011
-- value:    count
-- shape:    ranking
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   units sold (§2.2), by city
-- scope:    region IN-TN (Tamil Nadu)
-- currency: none
-- top_k:    10
-- rule:     units counts EVERY line -- phones AND accessories (§2.2). "Units sold" on
--           its own includes cases and chargers, so it is always larger than phones sold.
--           Units counts LINES, so an accessory belongs to itself and is not attributed
--           to the handset it was bought with -- unlike order-level money (§1.7a).
--           Only PAID orders contribute; lines on abandoned or cancelled orders are out.
-- excludes: test orders (§1.1); abandoned and cancelled orders (§2.2)
select ci.name as key, sum(i.qty) as value
from order_items i
join orders o on o.order_id = i.order_id
join showrooms s on s.showroom_id = o.showroom_id
join cities ci on ci.city_id = s.city_id
where not o.is_test and o.status = 'paid' and s.region_id = 'IN-TN'
  and o.business_date between date '2026-08-01' and date '2026-08-31'
group by ci.name order by value desc, key asc limit 10
