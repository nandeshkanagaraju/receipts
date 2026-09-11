-- qid:      HO-006
-- value:    ratio
-- shape:    scalar
-- window:   last_week          -> 2026-08-31 .. 2026-09-06   (GLOSSARY §1.6, as_of 2026-09-10)
-- metric:   payment success rate, ORDER-level (§2.8)
-- scope:    country GB (the asker's own scope, D7 -- store_ops_uk sees UK only)
-- currency: none (a ratio, §2.8)
-- rule:     "success rate" UNQUALIFIED is ORDER-level (§4.1, §6.1), never
--           attempt-level (§2.9). The two differ by a lot wherever customers retry,
--           and an answer that gives one must say which it gave.
--           Numerator: distinct orders with AT LEAST ONE captured attempt.
--           Denominator: distinct orders with AT LEAST ONE attempt. Orders where the
--           customer never attempted payment are in neither (§2.8).
--           Keyed on ORDER business date, which is the showroom's own local date
--           (§1.2, §4.5) -- never a UTC day.
--           "Last week" is the most recent COMPLETE Monday-to-Sunday week (§1.6), not
--           the last seven days; those are different windows.
--           No breakdown, so no attribution rule applies (§1.9 governs per-method
--           rates only).
--           Since ADR-014 an `authorized` attempt is not a capture (§4.2): the
--           numerator tests `status = 'captured'`, never `status <> 'failed'`.
-- excludes: test orders and test attempts (§1.1)
with attempted as (
    select a.order_id,
           max(case when a.status = 'captured' then 1 else 0 end) as succeeded
    from payment_attempts a
    join orders o on o.order_id = a.order_id
    join showrooms s on s.showroom_id = o.showroom_id
    where not a.is_test
      and not o.is_test
      and s.country_code = 'GB'
      and o.business_date between date '2026-08-31' and date '2026-09-06'
    group by a.order_id
)
select cast(sum(succeeded) * 1.0 / count(*) as decimal(38,12)) as value
from attempted
order by value
