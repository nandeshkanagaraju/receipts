-- qid:      EV-109
-- value:    ratio
-- shape:    ranking
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   payment success rate, order-level (§2.8), by payment method
-- scope:    country MY
-- currency: none
-- top_k:    5
-- rule:     "tried" attribution (§1.9): the denominator is orders that ATTEMPTED on that
--           method, the numerator those with a CAPTURED attempt on the SAME method. An
--           order that tried UPI, failed, then paid by card is in BOTH denominators -- a
--           failure for UPI and a success for card, and both are true.
--           Final-attempt attribution would make a method's rate RISE precisely when it is
--           failing, and the worse the outage the better the number, as long as customers
--           switch. A metric that improves during the incident it should detect is worse
--           than no metric.
--           These denominators OVERLAP, so the per-method rates do not sum, average or
--           otherwise reconcile to the overall order-level rate (§1.9).
-- excludes: test orders and test attempts (§1.1)
with scope as (
    select o.order_id
    from orders o
    join showrooms s on s.showroom_id = o.showroom_id
    where not o.is_test and s.country_code = 'MY'
      and o.business_date between date '2026-08-01' and date '2026-08-31'
),
tried as (
    select a.method, a.order_id,
           max(case when a.status = 'captured' then 1 else 0 end) as succeeded
    from payment_attempts a
    join scope sc on sc.order_id = a.order_id
    where not a.is_test
    group by a.method, a.order_id
)
select method as key, cast(sum(succeeded) * 1.0 / count(*) as decimal(38,12)) as value
from tried group by method order by value desc, key asc limit 5
