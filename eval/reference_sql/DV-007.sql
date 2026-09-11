-- qid:      DV-007
-- value:    count
-- shape:    ranking
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   units sold (§2.2)
-- scope:    country GB
-- currency: none
-- top_k:    5
-- rule:     units counts every line -- phones AND accessories (§2.2). A
--           showroom with a strong accessory business ranks higher on units
--           than on handsets, which is the intended reading of "units sold".
--           Only PAID orders contribute; lines on abandoned or cancelled
--           orders are excluded (§2.2). Keyed on the order business date of
--           the order the line belongs to.
-- excludes: test orders (§1.1); abandoned and cancelled orders
select s.name as key,
       sum(i.qty) as value
from order_items i
join orders o on o.order_id = i.order_id
join showrooms s on s.showroom_id = o.showroom_id
where not o.is_test
  and o.status = 'paid'
  and s.country_code = 'GB'
  and o.business_date between date '2026-08-01' and date '2026-08-31'
group by s.name
order by value desc, key asc
limit 5
