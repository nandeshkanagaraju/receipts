-- qid:      HO-B08
-- value:    money_minor
-- shape:    compare
-- window:   this_month_to_date -> 2026-09-01 .. 2026-09-09 against 2026-08-01 .. 2026-08-09
--           (the comparison window is the SAME DAYS of the previous month, §1.6a)
-- metric:   captured GMV (§2.3) by city
-- scope:    region IN-TN (Tamil Nadu)
-- currency: INR (§1.4 rule 2 -- rm_tamil_nadu reports in INR)
-- rule:     EQUAL-LENGTH WINDOWS (§1.6a, SDD §9.1 rule 5). "This month" is month-to-date
--           -- 1-9 September, NINE days -- and the comparison is the SAME NINE DAYS of
--           the previous month, 1-9 August. It is NOT the whole of August: comparing
--           nine days against thirty-one would show a collapse in every additive metric
--           every month, purely as an artefact of the calendar.
--           "Sales" unqualified is captured GMV -- money, not units (§6.1) -- and the
--           reading must be disclosed in the answer.
--           "Compare" makes this a CHANGE, not a level, so both values are returned per
--           city, keyed `<city>|current` and `<city>|comparison` (ADR-009). A system
--           that silently drops the comparison has not answered the question.
--           Every Tamil Nadu city is returned, because the question says "all"; a city
--           with no captures in a window is an exact zero rather than a missing row
--           (docs/M2_NOTES.md §5).
--           The scope is one region and one currency, so no conversion arises (§1.3).
-- excludes: test orders and test attempts (§1.1); duplicate captures (§4.10)
with captures as (
    select a.order_id, a.amount_minor, a.currency, a.business_date,
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
    select 'current' as label, date '2026-09-01' as lo, date '2026-09-09' as hi
    union all
    select 'comparison', date '2026-08-01', date '2026-08-09'
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
)
select sp.city_name || '|' || sp.label as key,
       cast(coalesce(v.amount, 0) as bigint) as value
from spine sp
left join valued v on v.city_name = sp.city_name and v.label = sp.label
order by key asc
