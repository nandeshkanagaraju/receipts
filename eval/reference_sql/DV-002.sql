-- qid:      DV-002
-- value:    count
-- shape:    scalar
-- window:   yesterday          -> 2026-09-09 .. 2026-09-09   (GLOSSARY §1.7, as_of 2026-09-10)
-- metric:   orders count (§2.1)
-- scope:    region IN-TN (Tamil Nadu)
-- currency: none
-- rule:     all three order statuses count -- paid, abandoned and cancelled
--           (§2.1). "How many orders did we take" is not "how many did we get
--           paid for". Keyed on order business date, which is the showroom's
--           own local date (§1.2, §4.5), never a UTC day.
-- excludes: test orders (§1.1)
select count(*) as value
from orders o
join showrooms s on s.showroom_id = o.showroom_id
where not o.is_test
  and s.region_id = 'IN-TN'
  and o.business_date = date '2026-09-09'
order by value
