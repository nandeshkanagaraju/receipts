-- qid:      EV-053
-- value:    count
-- shape:    scalar
-- window:   july_2026          -> 2026-07-01 .. 2026-07-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   units sold (§2.2)
-- scope:    country US
-- currency: none
-- rule:     units counts every line, accessories included (§2.2), on PAID orders only.
--           Test orders are excluded by the FLAG (§4.8), never by matching on names or
--           amounts -- doing that both misses tests and removes real business.
-- excludes: test orders (§1.1); abandoned and cancelled orders
select sum(i.qty) as value
from order_items i
join orders o on o.order_id = i.order_id
join showrooms s on s.showroom_id = o.showroom_id
where not o.is_test and o.status = 'paid' and s.country_code = 'US'
  and o.business_date between date '2026-07-01' and date '2026-07-31'
order by value
