-- qid:      EV-078
-- value:    ratio
-- shape:    ranking
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   payment success rate, order-level (§2.8), by country
-- scope:    all countries
-- currency: none
-- top_k:    6
-- rule:     unqualified "success rate" is ORDER-level (§4.1, §2.8).
--           The breakdown is geographical, not by method, so the §1.9 "tried" rule does
--           not enter: an order belongs to exactly one showroom and therefore one country,
--           and these denominators DO partition the orders. Contrast EV-010 and EV-114,
--           where per-method denominators overlap and the parts do not sum to the whole.
--           Denominator: orders with at least one payment attempt (§2.8).
-- excludes: test orders and test attempts (§1.1)
with attempted as (
    select o.order_id, s.country_code,
           max(case when a.status = 'captured' then 1 else 0 end) as paid
    from orders o
    join showrooms s on s.showroom_id = o.showroom_id
    join payment_attempts a on a.order_id = o.order_id and not a.is_test
    where not o.is_test
      and o.business_date between date '2026-08-01' and date '2026-08-31'
    group by o.order_id, s.country_code
)
select country_code as key, cast(sum(paid) * 1.0 / count(*) as decimal(38,12)) as value
from attempted group by country_code order by value desc, key asc limit 6
