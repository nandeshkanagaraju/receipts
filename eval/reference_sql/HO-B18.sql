-- qid:      HO-B18
-- value:    count
-- shape:    ranking
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   orders count (§2.1) by channel
-- scope:    country GB
-- currency: none (a count)
-- top_k:    2
-- rule:     the row carries an `interpretation` because the glossary governs the metric
--           but does not name the channel values: "online pickup" is the `online_pickup`
--           channel and "walk-in" is `in_store`.
--           ALL THREE ORDER STATUSES COUNT -- paid, abandoned and cancelled (§2.1,
--           §6.1). The question compares how many orders each channel took, not how many
--           were paid for, which is a different number (§5.2).
--           "Compare A vs B" here contrasts two DIMENSION VALUES, not two time windows,
--           so `compare` in the ADR-009 sense does not apply: there is one window and a
--           breakdown with two keys. A comparison flag would make the scorer look for
--           `current` and `comparison` labels that the question never asked for.
--           Keyed on ORDER business date (§2.1).
--           A channel with no orders is an exact zero rather than a missing row
--           (docs/M2_NOTES.md §5).
-- excludes: test orders (§1.1)
with scoped as (
    select o.order_id, o.channel, o.business_date
    from orders o
    join showrooms s on s.showroom_id = o.showroom_id
    where not o.is_test
      and s.country_code = 'GB'
),
spine as (
    select distinct channel from scoped
),
valued as (
    select channel, count(*) as orders
    from scoped
    where business_date between date '2026-08-01' and date '2026-08-31'
    group by channel
)
select sp.channel as key,
       cast(coalesce(v.orders, 0) as bigint) as value
from spine sp
left join valued v on v.channel = sp.channel
order by value desc, key asc
limit 2
