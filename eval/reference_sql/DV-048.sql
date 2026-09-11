-- qid:      DV-048
-- value:    ratio
-- shape:    ranking
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   payment success rate, order-level (§2.8), by issuing bank
-- scope:    city Chennai, UPI attempts only
-- currency: none
-- top_k:    10
-- rule:     "tried" attribution (§1.9): the denominator is orders that
--           ATTEMPTED UPI on that issuing bank, the numerator those that had a
--           CAPTURED UPI attempt on the SAME bank. Final-attempt attribution
--           would make a bank's rate rise precisely when that bank is failing,
--           because every customer who recovers on another bank leaves its
--           denominator.
--           Per-bank denominators OVERLAP and do not partition the orders, so
--           these rates cannot be combined to reproduce the overall rate (§1.9).
--           Keyed on ORDER business date (§2.8).
-- excludes: test orders and test attempts (§1.1)
with scope as (
    select o.order_id
    from orders o
    join showrooms s on s.showroom_id = o.showroom_id
    join cities ci on ci.city_id = s.city_id
    where not o.is_test
      and ci.name = 'Chennai'
      and o.business_date between date '2026-08-01' and date '2026-08-31'
),
tried as (
    select a.issuing_bank,
           a.order_id,
           max(case when a.status = 'captured' then 1 else 0 end) as succeeded
    from payment_attempts a
    join scope sc on sc.order_id = a.order_id
    where not a.is_test
      and a.method = 'upi'
      and a.issuing_bank is not null
    group by a.issuing_bank, a.order_id
)
select issuing_bank as key,
       cast(sum(succeeded) * 1.0 / count(*) as decimal(38,12)) as value
from tried
group by issuing_bank
order by value desc, key asc
limit 10
