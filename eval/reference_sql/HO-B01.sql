-- qid:      HO-B01
-- value:    count
-- shape:    scalar
-- window:   last_week          -> 2026-08-31 .. 2026-09-06   (GLOSSARY §1.6, as_of 2026-09-10)
-- metric:   orders count (§2.1)
-- scope:    city Chennai
-- currency: none (a count)
-- rule:     "How many orders did we take" is orders count, and ALL THREE STATUSES
--           COUNT -- paid, abandoned and cancelled (§2.1, §5.2, §6.1). "How many did we
--           get paid for" is a different and smaller number.
--           "Last week" is the most recent COMPLETE Monday-to-Sunday week (§1.6), not
--           the last seven days; those are different windows.
--           Keyed on ORDER business date, the showroom's own local date (§1.2, §4.5).
-- excludes: test orders (§1.1)
select count(*) as value
from orders o
join showrooms s on s.showroom_id = o.showroom_id
join cities ci on ci.city_id = s.city_id
where not o.is_test
  and ci.name = 'Chennai'
  and o.business_date between date '2026-08-31' and date '2026-09-06'
order by value
