-- qid:      DV-012
-- value:    ratio
-- shape:    scalar
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   NOT a Kestrel metric -- cancellation share, per the row's `interpretation`
-- scope:    city Chennai
-- currency: none
-- rule:     interpretation: "orders with status 'cancelled' divided by all
--           orders created in the window, both restricted to showrooms in
--           Chennai, keyed on order business date, excluding test orders."
--           The denominator is ALL orders, every status (§2.1), not paid ones.
-- excludes: test orders (§1.1)
select cast(
           sum(case when o.status = 'cancelled' then 1 else 0 end) * 1.0 / count(*)
       as decimal(38,12)) as value
from orders o
join showrooms s on s.showroom_id = o.showroom_id
join cities ci on ci.city_id = s.city_id
where not o.is_test
  and ci.name = 'Chennai'
  and o.business_date between date '2026-08-01' and date '2026-08-31'
order by value
