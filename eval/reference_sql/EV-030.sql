-- qid:      EV-030
-- value:    count
-- shape:    ranking
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   orders count (§2.1), by channel
-- scope:    country IN
-- currency: none
-- top_k:    2
-- rule:     all three order statuses count (§2.1) -- paid, abandoned and cancelled.
--           A channel split of orders_count partitions the orders, unlike a per-method
--           split of a success rate (§1.9).
-- excludes: test orders (§1.1)
select o.channel as key, count(*) as value
from orders o
join showrooms s on s.showroom_id = o.showroom_id
where not o.is_test and s.country_code = 'IN'
  and o.business_date between date '2026-08-01' and date '2026-08-31'
group by o.channel order by value desc, key asc limit 2
