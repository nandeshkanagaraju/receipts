-- qid:      DV-043
-- value:    ratio
-- shape:    compare
-- window:   last_week          -> 2026-08-31 .. 2026-09-06 against 2026-08-24 .. 2026-08-30
--           (the comparison window is the preceding complete week, §1.6, §1.6a)
-- metric:   payment success rate, order-level (§2.8)
-- scope:    country GB
-- currency: none
-- rule:     unqualified "success rate" is ORDER-level (§4.1, §2.8): the share
--           of orders that were eventually paid. A customer whose first attempt
--           fails and whose second succeeds has had one successful purchase;
--           counting them as one success out of two describes the plumbing, not
--           the shopping trip.
--           Denominator: orders with AT LEAST ONE payment attempt. Orders where
--           the customer never attempted payment are in neither numerator nor
--           denominator (§2.8).
--           Both weeks are complete Monday-Sunday weeks and equal length
--           (§1.6, §1.6a).
-- excludes: test orders and test attempts (§1.1)
with attempted as (
    select o.order_id,
           o.business_date,
           max(case when a.status = 'captured' then 1 else 0 end) as paid
    from orders o
    join showrooms s on s.showroom_id = o.showroom_id
    join payment_attempts a on a.order_id = o.order_id and not a.is_test
    where not o.is_test
      and s.country_code = 'GB'
      and (o.business_date between date '2026-08-31' and date '2026-09-06'
        or o.business_date between date '2026-08-24' and date '2026-08-30')
    group by o.order_id, o.business_date
)
select case when business_date >= date '2026-08-31' then 'current' else 'comparison' end as key,
       cast(sum(paid) * 1.0 / count(*) as decimal(38,12)) as value
from attempted
group by key
order by key asc
