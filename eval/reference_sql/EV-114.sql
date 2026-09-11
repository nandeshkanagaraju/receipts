-- qid:      EV-114
-- value:    ratio
-- shape:    ranking
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   payment success rate, order-level (§2.8), by issuing bank
-- scope:    country GB, pay-later attempts only
-- currency: none
-- top_k:    10
-- rule:     "pay-later orders" here qualifies which ATTEMPTS are in scope for a success
--           rate, so §1.9's "tried" rule governs: the denominator is orders that ATTEMPTED
--           pay-later on that issuing bank, the numerator those with a CAPTURED pay-later
--           attempt on the SAME bank.
--           This is the one place the two order-attribution rules could be confused. §5.3a
--           ("orders whose CAPTURED attempt used that method") filters a SET of orders and
--           is used for value metrics; §1.9 attributes a SUCCESS RATE, and using §5.3a
--           here would put only successful orders in the denominator and drive every rate
--           to 100%.
--           Per-bank denominators OVERLAP and do not reconcile to the overall rate (§1.9).
-- excludes: test orders and test attempts (§1.1)
with scope as (
    select o.order_id
    from orders o
    join showrooms s on s.showroom_id = o.showroom_id
    where not o.is_test and s.country_code = 'GB'
      and o.business_date between date '2026-08-01' and date '2026-08-31'
),
tried as (
    select a.issuing_bank, a.order_id,
           max(case when a.status = 'captured' then 1 else 0 end) as succeeded
    from payment_attempts a
    join scope sc on sc.order_id = a.order_id
    where not a.is_test and a.method = 'pay_later' and a.issuing_bank is not null
    group by a.issuing_bank, a.order_id
)
select issuing_bank as key, cast(sum(succeeded) * 1.0 / count(*) as decimal(38,12)) as value
from tried group by issuing_bank order by value desc, key asc limit 10
