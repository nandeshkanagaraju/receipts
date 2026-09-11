-- qid:      EV-010
-- value:    ratio
-- shape:    ranking
-- window:   last_week          -> 2026-08-31 .. 2026-09-06   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   payment success rate, order-level (§2.8), by card network
-- scope:    country GB, card attempts only
-- currency: none
-- top_k:    5
-- rule:     the "tried" attribution rule (§1.9): the denominator is orders that
--           ATTEMPTED on that network, the numerator those with a CAPTURED attempt on the
--           SAME network. An order that failed on one and paid on another counts as a
--           failure for the first and a success for the second -- both are true.
--           Final-attempt attribution would make a network's rate RISE precisely when it is
--           failing, because every customer who recovers elsewhere leaves its denominator.
--           Per-network denominators OVERLAP, so these rates do not sum or reconcile to the
--           overall order-level rate (§1.9). Keyed on ORDER business date (§2.8).
-- excludes: test orders and test attempts (§1.1)
with scope as (
    select o.order_id
    from orders o
    join showrooms s on s.showroom_id = o.showroom_id
    where not o.is_test
      and s.country_code = 'GB'
      and o.business_date between date '2026-08-31' and date '2026-09-06'
),
tried as (
    select a.card_network, a.order_id,
           max(case when a.status = 'captured' then 1 else 0 end) as succeeded
    from payment_attempts a
    join scope sc on sc.order_id = a.order_id
    where not a.is_test and a.method = 'card' and a.card_network is not null
    group by a.card_network, a.order_id
)
select card_network as key,
       cast(sum(succeeded) * 1.0 / count(*) as decimal(38,12)) as value
from tried group by card_network order by value desc, key asc limit 5
