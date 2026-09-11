-- qid:      EV-066
-- value:    ratio
-- shape:    series
-- window:   last_7_days        -> 2026-09-03 .. 2026-09-09   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   payment success rate, order-level (§2.8), daily
-- scope:    country GB
-- currency: none
-- rule:     a SERIES matched by TIME KEY, not by rank (ADR-009); no top_k.
--           Unqualified "success rate" is ORDER-level (§4.1, §2.8): denominator is orders
--           with at least one payment attempt, numerator those that reached paid.
--           Keyed on ORDER business date, so a retry on a later day still belongs to its
--           order's day -- which is why this is not the attempt-level rate of §2.9.
--           "Last 7 days" ends YESTERDAY; the reporting day is excluded (§1.6a).
-- excludes: test orders and test attempts (§1.1)
with attempted as (
    select o.order_id, o.business_date,
           max(case when a.status = 'captured' then 1 else 0 end) as paid
    from orders o
    join showrooms s on s.showroom_id = o.showroom_id
    join payment_attempts a on a.order_id = o.order_id and not a.is_test
    where not o.is_test and s.country_code = 'GB'
      and o.business_date between date '2026-09-03' and date '2026-09-09'
    group by o.order_id, o.business_date
)
select cast(business_date as varchar) as key,
       cast(sum(paid) * 1.0 / count(*) as decimal(38,12)) as value
from attempted group by business_date order by key asc
