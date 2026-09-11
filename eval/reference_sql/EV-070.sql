-- qid:      EV-070
-- value:    count
-- shape:    scalar
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   units sold (§2.2)
-- scope:    region IN-TN (Tamil Nadu) -- the asker's own scope
-- currency: none
-- rule:     "we" resolves to the asker's scope, Tamil Nadu, injected from auth context
--           and never present in the question (D7).
--           Units counts every line -- phones AND accessories (§2.2) -- so this is larger
--           than the handset count. Only PAID orders contribute.
-- excludes: test orders (§1.1); abandoned and cancelled orders
select sum(i.qty) as value
from order_items i
join orders o on o.order_id = i.order_id
join showrooms s on s.showroom_id = o.showroom_id
where not o.is_test and o.status = 'paid' and s.region_id = 'IN-TN'
  and o.business_date between date '2026-08-01' and date '2026-08-31'
order by value
