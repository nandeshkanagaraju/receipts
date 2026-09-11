-- qid:      DV-028
-- value:    ratio
-- shape:    scalar
-- window:   last_week          -> 2026-08-31 .. 2026-09-06   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   payment success rate, ATTEMPT-level (§2.9)
-- scope:    city Chennai, UPI attempts only
-- currency: none
-- rule:     the question names attempt-level explicitly, so this is §2.9 and
--           not §2.8: the share of individual ATTEMPTS captured, denominator
--           all attempts of any outcome. Attempt-level needs no attribution
--           rule -- every attempt already carries its own method (§1.9).
--           It is ALWAYS LOWER than the order-level rate wherever customers
--           retry, and the two must never be compared as the same measure
--           (§2.9). Compare with DV-001, which is the order-level figure.
--           Keyed on ATTEMPT business date (§2.9), not order business date.
-- excludes: test attempts (§1.1)
select cast(
           sum(case when a.status = 'captured' then 1 else 0 end) * 1.0 / count(*)
       as decimal(38,12)) as value
from payment_attempts a
join orders o on o.order_id = a.order_id
join showrooms s on s.showroom_id = o.showroom_id
join cities ci on ci.city_id = s.city_id
where not a.is_test
  and a.method = 'upi'
  and ci.name = 'Chennai'
  and a.business_date between date '2026-08-31' and date '2026-09-06'
order by value
