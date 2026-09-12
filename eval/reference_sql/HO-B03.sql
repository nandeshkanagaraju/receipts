-- qid:      HO-B03
-- value:    ratio
-- shape:    scalar
-- window:   yesterday          -> 2026-09-09 .. 2026-09-09   (GLOSSARY §1.7, as_of 2026-09-10)
-- metric:   payment success rate, ORDER-level (§2.8), for one method
-- scope:    region IN-TN (Tamil Nadu), method UPI
-- currency: none (a ratio)
-- rule:     "Success rate" UNQUALIFIED is ORDER-level (§4.1, §6.1), never attempt-level
--           (§2.9). The two differ by a lot wherever customers retry -- which is
--           everywhere UPI is used.
--           Broken down by method it uses "TRIED" ATTRIBUTION (§1.9, §6.1): the
--           denominator is orders that ATTEMPTED on UPI, the numerator those that had a
--           CAPTURED UPI attempt. An order that failed on UPI and then paid by card
--           counts as a UPI failure and a card success.
--           Final-attempt attribution would remove exactly those orders from UPI's
--           denominator, so UPI's rate would RISE precisely when UPI is failing (§1.9).
--           Per-method rates do not sum or reconcile to the overall rate, because the
--           denominators overlap (§1.9).
--           "Yesterday" is the showroom's own local business date (§1.7, §4.5); in India
--           a UTC day would start at 5:30 a.m. local and pull in the wrong day.
--           Since ADR-014 an `authorized` attempt is not a capture (§4.2).
-- excludes: test orders and test attempts (§1.1)
with tried_upi as (
    select a.order_id,
           max(case when a.status = 'captured' then 1 else 0 end) as succeeded
    from payment_attempts a
    join orders o on o.order_id = a.order_id
    join showrooms s on s.showroom_id = o.showroom_id
    where not a.is_test
      and not o.is_test
      and a.method = 'upi'
      and s.region_id = 'IN-TN'
      and o.business_date = date '2026-09-09'
    group by a.order_id
)
select cast(sum(succeeded) * 1.0 / count(*) as decimal(38,12)) as value
from tried_upi
order by value
