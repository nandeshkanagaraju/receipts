-- qid:      DV-001
-- value:    ratio
-- shape:    scalar
-- window:   yesterday          -> 2026-09-09 .. 2026-09-09   (GLOSSARY §1.7, as_of 2026-09-10)
-- metric:   payment success rate, order-level (§2.8), broken down by method
-- scope:    city Chennai
-- currency: none
-- rule:     "success rate" unqualified is ORDER-level (§4.1), not attempt-level.
--           Broken down by method it uses "tried" attribution (§1.9): the
--           denominator is orders that ATTEMPTED on UPI, the numerator those
--           that had a CAPTURED UPI attempt. Final-attempt attribution would
--           make UPI's rate rise when UPI fails.
-- excludes: test orders and test attempts (§1.1)
with scope as (
    select o.order_id
    from orders o
    join showrooms s on s.showroom_id = o.showroom_id
    join cities ci on ci.city_id = s.city_id
    where not o.is_test
      and ci.name = 'Chennai'
      and o.business_date = date '2026-09-09'
),
tried_upi as (
    select a.order_id,
           max(case when a.status = 'captured' then 1 else 0 end) as succeeded
    from payment_attempts a
    join scope sc on sc.order_id = a.order_id
    where not a.is_test
      and a.method = 'upi'
    group by a.order_id
)
select cast(sum(succeeded) * 1.0 / count(*) as decimal(38,12)) as value
from tried_upi
order by value
