-- qid:      EV-054
-- value:    count
-- shape:    scalar
-- window:   last_week          -> 2026-08-31 .. 2026-09-06   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   payment attempts, a plain count (attempt-level, §2.9 denominator)
-- scope:    region IN-TN (Tamil Nadu)
-- currency: none
-- rule:     attempts of ANY outcome, captured and failed alike -- the attempts side of
--           §4.1, not an order count. Keyed on ATTEMPT business date.
--           Test attempts are excluded by the flag (§4.8).
-- excludes: test attempts (§1.1)
select count(*) as value
from payment_attempts a
join orders o on o.order_id = a.order_id
join showrooms s on s.showroom_id = o.showroom_id
where not a.is_test and s.region_id = 'IN-TN'
  and a.business_date between date '2026-08-31' and date '2026-09-06'
order by value
