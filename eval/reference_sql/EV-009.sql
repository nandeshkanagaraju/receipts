-- qid:      EV-009
-- value:    count
-- shape:    scalar
-- window:   july_2026          -> 2026-07-01 .. 2026-07-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   orders count (§2.1)
-- scope:    country MY
-- currency: none
-- rule:     all three order statuses count -- paid, abandoned and cancelled (§2.1).
--           "How many orders did we take" is not "how many did we get paid for".
--           Test orders are excluded by the FLAG, never by matching on names or amounts
--           (§4.8): they are a small share of rows, which is exactly why they survive --
--           they move a number by a few percent, which looks like noise, not a bug.
-- excludes: test orders (§1.1)
select count(*) as value
from orders o
join showrooms s on s.showroom_id = o.showroom_id
where not o.is_test
  and s.country_code = 'MY'
  and o.business_date between date '2026-07-01' and date '2026-07-31'
order by value
