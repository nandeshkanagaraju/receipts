-- qid:      HO-007
-- value:    count
-- shape:    scalar
-- window:   july_2026          -> 2026-07-01 .. 2026-07-31   (on ATTEMPT business date)
-- metric:   payment attempts, of any outcome -- the §2.9 denominator
-- scope:    all countries
-- currency: none (a count)
-- rule:     every attempt counts whatever its outcome -- captured, authorised and
--           failed alike (§2.9's denominator). This is an ATTEMPT-level count, not an
--           order count: a customer who fails once and succeeds on the retry produces
--           two attempts and one paid order (§4.1).
--           Test transactions are excluded on BOTH sides: the attempt's own flag and
--           the joined order's. They are a small share of rows, which is exactly why
--           they survive -- they move a number by a few percent, which looks like
--           noise rather than a bug (§4.8). They are never excluded by matching on
--           names or amounts (§1.1).
--           Keyed on the attempt's own business date, the showroom's local date
--           (§1.2, §4.5).
-- excludes: test attempts and test orders (§1.1, §4.8)
select count(*) as value
from payment_attempts a
join orders o on o.order_id = a.order_id
where not a.is_test
  and not o.is_test
  and a.business_date between date '2026-07-01' and date '2026-07-31'
order by value
