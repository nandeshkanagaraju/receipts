-- qid:      EV-107
-- value:    count
-- shape:    ranking
-- window:   last_week          -> 2026-08-31 .. 2026-09-06   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   orders count (§2.1), by city
-- scope:    country GB
-- currency: none
-- top_k:    10
-- rule:     all three order statuses count (§2.1). "Rank the cities by order count"
--           names the quantity, so it is not the undefined "best" (§5.5).
--           "Last week" is the most recent complete Monday-Sunday week (§1.6).
-- excludes: test orders (§1.1)
select ci.name as key, count(*) as value
from orders o
join showrooms s on s.showroom_id = o.showroom_id
join cities ci on ci.city_id = s.city_id
where not o.is_test and s.country_code = 'GB'
  and o.business_date between date '2026-08-31' and date '2026-09-06'
group by ci.name order by value desc, key asc limit 10
