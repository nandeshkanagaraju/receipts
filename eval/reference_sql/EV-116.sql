-- qid:      EV-116
-- value:    count
-- shape:    scalar
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   NOT a Kestrel metric -- accessory units, per the row's `interpretation`
-- scope:    region IN-TN (Tamil Nadu)
-- currency: none
-- rule:     interpretation: "total quantity across order lines whose product is an
--           accessory, on non-test paid orders at Tamil Nadu showrooms in the window,
--           keyed on order business date."
--           Units sold (§2.2) counts handsets and accessories TOGETHER; an
--           accessories-only count is the filtered complement of the handsets-only count
--           and is not separately defined, which is why this row is annotated.
--           Units counts LINES, so an accessory is its own unit (§2.2, §1.7a).
-- excludes: test orders (§1.1); abandoned and cancelled orders
select sum(i.qty) as value
from order_items i
join orders o on o.order_id = i.order_id
join products p on p.sku = i.sku
join showrooms s on s.showroom_id = o.showroom_id
where not o.is_test and o.status = 'paid' and p.is_accessory
  and s.region_id = 'IN-TN'
  and o.business_date between date '2026-08-01' and date '2026-08-31'
order by value
