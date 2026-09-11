-- qid:      DV-023
-- value:    count
-- shape:    scalar
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   payment attempts, a plain count (attempt-level, §2.9 denominator)
-- scope:    country SG
-- currency: none
-- rule:     attempts of ANY outcome -- captured and failed alike. This is the
--           attempts-versus-orders distinction (§4.1): a customer who fails
--           once and succeeds on the retry is two attempts and one order.
--           Test attempts are excluded by the FLAG, never by matching on names
--           or amounts (§4.8) -- they are a small share of rows, which is
--           exactly why they survive.
-- excludes: test attempts (§1.1)
select count(*) as value
from payment_attempts a
join orders o on o.order_id = a.order_id
join showrooms s on s.showroom_id = o.showroom_id
where not a.is_test
  and s.country_code = 'SG'
  and a.business_date between date '2026-08-01' and date '2026-08-31'
order by value
