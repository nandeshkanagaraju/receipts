-- qid:      EV-004
-- value:    ratio
-- shape:    scalar
-- window:   last_week          -> 2026-08-31 .. 2026-09-06   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   payment success rate, order-level (§2.8)
-- scope:    country SG
-- currency: none
--           unqualified "success rate" is ORDER-level (§4.1, §2.8), not attempt-level.
--           Denominator: orders with AT LEAST ONE payment attempt; orders where the
--           customer never attempted payment are in neither side. Keyed on ORDER
--           business date. "Last week" is the most recent complete Monday-Sunday week,
--           not the last seven days (§1.6).
-- excludes: test orders and test attempts (§1.1)
with attempted as (
    select o.order_id,
           max(case when a.status = 'captured' then 1 else 0 end) as paid
    from orders o
    join showrooms s on s.showroom_id = o.showroom_id
    join payment_attempts a on a.order_id = o.order_id and not a.is_test
    where not o.is_test
      and s.country_code = 'SG'
      and o.business_date between date '2026-08-31' and date '2026-09-06'
    group by o.order_id
)
select cast(sum(paid) * 1.0 / count(*) as decimal(38,12)) as value
from attempted
order by value
