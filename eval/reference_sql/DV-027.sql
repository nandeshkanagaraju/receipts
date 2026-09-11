-- qid:      DV-027
-- value:    count
-- shape:    scalar
-- window:   yesterday          -> 2026-09-09 .. 2026-09-09   (GLOSSARY §1.7, as_of 2026-09-10)
-- metric:   orders count (§2.1)
-- scope:    country GB
-- currency: none
-- rule:     "yesterday" is the SHOWROOM'S OWN local business date, one day
--           before the reporting date (§1.7) -- not the 24 hours before
--           midnight UTC, which for a UK showroom in September is offset by an
--           hour and pulls in the wrong evening (§4.5). The local date is
--           stored on every fact row, so no timestamp arithmetic is needed.
--           All three order statuses count (§2.1).
-- excludes: test orders (§1.1)
select count(*) as value
from orders o
join showrooms s on s.showroom_id = o.showroom_id
where not o.is_test
  and s.country_code = 'GB'
  and o.business_date = date '2026-09-09'
order by value
