-- qid:      EV-061
-- value:    count
-- shape:    ranking
-- window:   yesterday          -> 2026-09-09 .. 2026-09-09   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   orders count (§2.1), by country
-- scope:    all countries
-- currency: none
-- top_k:    6
-- rule:     "yesterday" resolves PER SHOWROOM in that showroom's own timezone (§1.7):
--           every showroom's 9 September is included even though Chennai's and London's
--           are different absolute moments. A single UTC window would be the wrong day in
--           four of the six countries (§4.5).
--           All three order statuses count (§2.1).
-- excludes: test orders (§1.1)
select s.country_code as key, count(*) as value
from orders o
join showrooms s on s.showroom_id = o.showroom_id
where not o.is_test and o.business_date = date '2026-09-09'
group by s.country_code order by value desc, key asc limit 6
