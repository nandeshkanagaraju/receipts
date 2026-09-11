-- qid:      EV-073
-- value:    ratio
-- shape:    scalar
-- window:   july_2026          -> 2026-07-01 .. 2026-07-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   payment success rate, ATTEMPT-level (§2.9)
-- scope:    country GB
-- currency: none
-- rule:     the question asks what share of ATTEMPTS succeeded, so this is §2.9 and not
--           §2.8: numerator is attempts that reached captured, denominator is attempts of
--           any outcome. Keyed on ATTEMPT business date.
--           Attempt-level is ALWAYS LOWER than order-level wherever customers retry, and
--           the two must never be compared as the same measure (§2.9). Attempt-level needs
--           no attribution rule: every attempt carries its own method and bank (§1.9).
-- excludes: test attempts (§1.1)
select cast(
           sum(case when a.status = 'captured' then 1 else 0 end) * 1.0 / count(*)
       as decimal(38,12)) as value
from payment_attempts a
join orders o on o.order_id = a.order_id
join showrooms s on s.showroom_id = o.showroom_id
where not a.is_test and s.country_code = 'GB'
  and a.business_date between date '2026-07-01' and date '2026-07-31'
order by value
