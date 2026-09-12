-- qid:      HO-042
-- value:    money_minor
-- shape:    compare
-- window:   august_2026        -> 2026-08-01 .. 2026-08-31 against 2026-07-01 .. 2026-07-31
--           (the two whole months the question names; equal-length, §1.6a)
-- metric:   captured GMV (§2.3) by city
-- scope:    region IN-TN (Tamil Nadu)
-- currency: INR (§1.4 rule 1 -- the asker named it)
-- top_k:    10
-- rule:     the question names both months explicitly, so no window token has to be
--           resolved against as_of: August is `current`, July is `comparison`. They are
--           whole calendar months of 31 days each, so the equal-length rule is satisfied
--           as written (§1.6a, SDD §9.1 rule 5).
--           "Increased the most" is a CHANGE, not a level, so `compare: true` applies and
--           BOTH values are returned per city, keyed `<city>|current` and
--           `<city>|comparison` (ADR-009). A system that answered with one number per
--           city -- even the right delta -- has not returned what a comparison question
--           asks for, and the scorer checks both.
--           The ranking is by the increase, so the cities are ordered by
--           August minus July descending; a city that fell ranks last rather than being
--           dropped, because "which increased the most" is answered over all of them.
--           Captured money only, never authorised (§4.2); the duplicate side of a
--           duplicate capture is counted once (§4.10).
--           Keyed on capture business date (§2.3).
--           A city with no captures in a month is an exact zero rather than a missing
--           row (docs/M2_NOTES.md §5).
--           The scope is one region and one currency, so no conversion arises (§1.3).
-- excludes: test orders and test attempts (§1.1); duplicate captures
with captures as (
    select a.order_id, a.amount_minor, a.business_date,
           row_number() over (
               partition by a.order_id, a.amount_minor
               order by a.attempt_no, a.attempt_id
           ) as capture_rank
    from payment_attempts a
    where a.status = 'captured'
      and not a.is_test
),
scoped_orders as (
    select o.order_id, ci.name as city_name
    from orders o
    join showrooms s on s.showroom_id = o.showroom_id
    join cities ci on ci.city_id = s.city_id
    where not o.is_test
      and s.region_id = 'IN-TN'
),
windows as (
    select 'current' as label, date '2026-08-01' as lo, date '2026-08-31' as hi
    union all
    select 'comparison', date '2026-07-01', date '2026-07-31'
),
spine as (
    select sc.city_name, w.label
    from (select distinct city_name from scoped_orders) sc
    cross join windows w
),
valued as (
    select so.city_name, w.label, sum(c.amount_minor) as amount
    from captures c
    join scoped_orders so on so.order_id = c.order_id
    join windows w on c.business_date between w.lo and w.hi
    where c.capture_rank = 1
    group by so.city_name, w.label
),
filled as (
    select sp.city_name,
           sp.label,
           cast(coalesce(v.amount, 0) as bigint) as value
    from spine sp
    left join valued v on v.city_name = sp.city_name and v.label = sp.label
),
ranked as (
    select city_name,
           sum(case when label = 'current' then value else -value end) as increase
    from filled
    group by city_name
    order by increase desc, city_name asc
    limit 10
)
select f.city_name || '|' || f.label as key,
       f.value as value
from filled f
join ranked r on r.city_name = f.city_name
order by key asc
