-- qid:      HO-B02
-- value:    count
-- shape:    ranking
-- window:   this_month_to_date -> 2026-09-01 .. 2026-09-09   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   units sold (§2.2), HANDSETS ONLY, by showroom
-- scope:    region IN-TN (Tamil Nadu)
-- currency: none (a count)
-- top_k:    1
-- rule:     "Sold the most PHONES" means handsets only (§2.2, §5.2); accessories are
--           excluded. A showroom with a strong accessory business ranks higher on units
--           than on handsets, so the two readings give different winners.
--           "This month" is month-to-date and ends YESTERDAY (§1.6a, §5.4): the
--           reporting day is excluded because it is not over.
--           Only PAID orders contribute (§2.2); quantity is summed, so two of the same
--           phone on one order counts as two.
--           The question asks WHICH showroom, so the answer is the single top row; ties
--           are a scoring matter, not a reason to return more.
--           Keyed on the order business date of the order the line belongs to (§2.2).
-- excludes: test orders (§1.1); accessories; abandoned and cancelled orders
select s.name as key,
       cast(sum(i.qty) as bigint) as value
from order_items i
join orders o on o.order_id = i.order_id
join showrooms s on s.showroom_id = o.showroom_id
join products p on p.sku = i.sku
where not o.is_test
  and o.status = 'paid'
  and not p.is_accessory
  and s.region_id = 'IN-TN'
  and o.business_date between date '2026-09-01' and date '2026-09-09'
group by s.name
order by value desc, key asc
limit 1
