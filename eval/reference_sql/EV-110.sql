-- qid:      EV-110
-- value:    count
-- shape:    ranking
-- window:   july_2026          -> 2026-07-01 .. 2026-07-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   units sold (§2.2), by channel
-- scope:    country SG
-- currency: none
-- top_k:    2
-- rule:     units counts every line, accessories included (§2.2), on PAID orders only.
--           A channel split of units partitions the lines.
-- excludes: test orders (§1.1); abandoned and cancelled orders
select o.channel as key, sum(i.qty) as value
from order_items i
join orders o on o.order_id = i.order_id
join showrooms s on s.showroom_id = o.showroom_id
where not o.is_test and o.status = 'paid' and s.country_code = 'SG'
  and o.business_date between date '2026-07-01' and date '2026-07-31'
group by o.channel order by value desc, key asc limit 2
