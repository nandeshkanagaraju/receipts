-- qid:      EV-120
-- value:    ratio
-- shape:    series
-- window:   last_7_days        -> 2026-09-03 .. 2026-09-09   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   payment success rate, order-level (§2.8), daily, for UPI
-- scope:    city Chennai, UPI attempts only
-- currency: none
-- rule:     a SERIES matched by TIME KEY, not by rank (ADR-009); no top_k.
--           Unqualified "success rate" is ORDER-level (§4.1); broken down by method it
--           uses "tried" attribution (§1.9): denominator is orders that ATTEMPTED UPI,
--           numerator those with a CAPTURED UPI attempt.
--           Keyed on ORDER business date (§2.8), so a retry the next day still belongs to
--           its order's day. That is why this differs from a daily attempt-level rate.
--           "Last 7 days" ends YESTERDAY; the reporting day is excluded (§1.6a).
-- excludes: test orders and test attempts (§1.1)
with scope as (
    select o.order_id, o.business_date
    from orders o
    join showrooms s on s.showroom_id = o.showroom_id
    join cities ci on ci.city_id = s.city_id
    where not o.is_test and ci.name = 'Chennai'
      and o.business_date between date '2026-09-03' and date '2026-09-09'
),
tried as (
    select sc.business_date, a.order_id,
           max(case when a.status = 'captured' then 1 else 0 end) as succeeded
    from payment_attempts a
    join scope sc on sc.order_id = a.order_id
    where not a.is_test and a.method = 'upi'
    group by sc.business_date, a.order_id
)
select cast(business_date as varchar) as key,
       cast(sum(succeeded) * 1.0 / count(*) as decimal(38,12)) as value
from tried group by business_date order by key asc
