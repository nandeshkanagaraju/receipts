-- qid:      DV-010
-- value:    ratio
-- shape:    ranking
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   payment success rate, order-level (§2.8), broken down by issuing bank
-- scope:    country GB, card attempts only
-- currency: none
-- top_k:    10
-- rule:     "tried" attribution (§1.9). Denominator: orders with at least one
--           non-test CARD attempt on that issuing bank. Numerator: those same
--           orders that had a CAPTURED card attempt on that SAME bank. An order
--           that failed on one bank and paid on another counts as a failure for
--           the first and a success for the second -- both are true.
--           Per-bank denominators OVERLAP, so these rates do not sum or
--           reconcile to the overall order-level rate (§1.9).
--           Keyed on order business date (§2.8), not attempt date.
-- excludes: test orders and test attempts (§1.1)
with scope as (
    select o.order_id
    from orders o
    join showrooms s on s.showroom_id = o.showroom_id
    where not o.is_test
      and s.country_code = 'GB'
      and o.business_date between date '2026-08-01' and date '2026-08-31'
),
tried as (
    select a.issuing_bank,
           a.order_id,
           max(case when a.status = 'captured' then 1 else 0 end) as succeeded
    from payment_attempts a
    join scope sc on sc.order_id = a.order_id
    where not a.is_test
      and a.method = 'card'
      and a.issuing_bank is not null
    group by a.issuing_bank, a.order_id
)
select issuing_bank as key,
       cast(sum(succeeded) * 1.0 / count(*) as decimal(38,12)) as value
from tried
group by issuing_bank
order by value desc, key asc
limit 10
