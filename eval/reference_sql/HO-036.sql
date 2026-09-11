-- qid:      HO-036
-- value:    count
-- shape:    series
-- window:   mar_to_aug_2026    -> 2026-03-01 .. 2026-08-31   (six whole calendar months)
-- metric:   orders count (§2.1), monthly
-- scope:    country SG
-- currency: none (a count)
-- rule:     a SERIES: matched by time key, not by rank (ADR-009), and carrying no
--           top_k. A rank comparison would pass a result whose months were right but
--           misordered, which for a series is the entire answer.
--           ALL THREE ORDER STATUSES COUNT -- paid, abandoned and cancelled (§2.1,
--           §6.1). "How many orders" unqualified is every status; "how many did we get
--           paid for" is a different and smaller number (§5.2).
--           The months are calendar months on business dates (§5.4), each keyed on the
--           order's own showroom-local business date (§1.2, §4.5). All six are whole
--           months inside the loaded range, so none is trimmed (§1.8).
--           Every month returns a row. A month with no orders would be an exact zero
--           rather than a missing row (docs/M2_NOTES.md §5).
--           Test orders are excluded by the flag, always (§1.1, §4.8).
-- excludes: test orders (§1.1, §4.8)
with months as (
    select * from (values
        (date '2026-03-01', date '2026-03-31'),
        (date '2026-04-01', date '2026-04-30'),
        (date '2026-05-01', date '2026-05-31'),
        (date '2026-06-01', date '2026-06-30'),
        (date '2026-07-01', date '2026-07-31'),
        (date '2026-08-01', date '2026-08-31')
    ) as t(lo, hi)
),
valued as (
    select m.lo, count(*) as orders
    from orders o
    join showrooms s on s.showroom_id = o.showroom_id
    join months m on o.business_date between m.lo and m.hi
    where not o.is_test
      and s.country_code = 'SG'
    group by m.lo
)
select cast(m.lo as varchar) as key,
       cast(coalesce(v.orders, 0) as bigint) as value
from months m
left join valued v on v.lo = m.lo
order by key asc
