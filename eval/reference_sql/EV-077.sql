-- qid:      EV-077
-- value:    count
-- shape:    ranking
-- window:   last_week          -> 2026-08-31 .. 2026-09-06   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   orders count (§2.1), by showroom
-- scope:    country GB
-- currency: none
-- top_k:    10
-- rule:     all three order statuses count (§2.1).
--           "Last week" is the most recent COMPLETE Monday-Sunday week, not the last seven
--           days -- they are different windows (§1.6).
-- excludes: test orders (§1.1)
select s.name as key, count(*) as value
from orders o
join showrooms s on s.showroom_id = o.showroom_id
where not o.is_test and s.country_code = 'GB'
  and o.business_date between date '2026-08-31' and date '2026-09-06'
group by s.name order by value desc, key asc limit 10
