-- qid:      DV-011
-- value:    ratio
-- shape:    scalar
-- window:   all_loaded         -> 2025-03-01 .. 2026-09-09   (GLOSSARY §1.8; the question names no window)
-- metric:   NOT a Kestrel metric -- attempts per order, per the row's `interpretation`
-- scope:    country IN
-- currency: none
-- rule:     interpretation: "total non-test payment attempts at Indian
--           showrooms in the window, divided by the number of distinct orders
--           having at least one such attempt. Keyed on attempt business date."
--           FLAG: the question states no window, so the whole loaded range is
--           used and the header says so. See the M3 report.
-- excludes: test attempts (§1.1)
with scoped as (
    select a.attempt_id, a.order_id
    from payment_attempts a
    join orders o on o.order_id = a.order_id
    join showrooms s on s.showroom_id = o.showroom_id
    where not a.is_test
      and s.country_code = 'IN'
      and a.business_date between date '2025-03-01' and date '2026-09-09'
)
select cast(count(*) * 1.0 / count(distinct order_id) as decimal(38,12)) as value
from scoped
order by value
