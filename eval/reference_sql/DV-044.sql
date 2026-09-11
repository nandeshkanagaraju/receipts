-- qid:      DV-044
-- value:    count
-- shape:    series
-- window:   last_7_days        -> 2026-09-03 .. 2026-09-09   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   orders count (§2.1), daily
-- scope:    region IN-TN (Tamil Nadu)
-- currency: none
-- rule:     a SERIES: matched by time key, not by rank (ADR-009). A rank
--           comparison would pass a result whose days were right but
--           misordered, which for a series is the entire answer. It carries no
--           top_k.
--           "The last 7 days" is the seven days ending YESTERDAY (§1.6a): the
--           reporting day is excluded because it is not over, and including a
--           partial day would understate that day's figure. This is a different
--           window from "last week" (§1.6).
--           Each day is the SHOWROOM'S local business date (§1.7, §4.5).
-- excludes: test orders (§1.1)
select cast(o.business_date as varchar) as key,
       count(*) as value
from orders o
join showrooms s on s.showroom_id = o.showroom_id
where not o.is_test
  and s.region_id = 'IN-TN'
  and o.business_date between date '2026-09-03' and date '2026-09-09'
group by o.business_date
order by key asc
