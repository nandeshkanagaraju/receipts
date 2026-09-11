-- qid:      HO-039
-- value:    ratio
-- shape:    series
-- window:   last_8_weeks       -> 2026-07-13 .. 2026-09-06   (eight COMPLETE weeks, §1.6a)
-- metric:   accessory attach rate (§2.12), weekly
-- scope:    country MY
-- currency: none (a ratio, §2.12)
-- rule:     a SERIES: matched by time key, not by rank (ADR-009), and carrying no
--           top_k. Each key is the week's MONDAY (§1.6: a week starts Monday).
--           "Last 8 weeks" is eight COMPLETE Monday-to-Sunday weeks (§1.6a). The
--           current partial week is EXCLUDED, not counted as one of the eight, so the
--           window runs Monday 2026-07-13 to Sunday 2026-09-06.
--           Attach rate is a count of ORDERS, not a split of money, so §1.7a's handset
--           attribution does not apply (§2.12, §1.7a).
--           Numerator: paid orders with at least one phone line AND at least one
--           accessory line. Denominator: paid orders with at least one phone line
--           (§2.12). Accessory-only orders would be in neither; in Kestrel's data every
--           order carries exactly one handset, so the denominator is every paid order.
--           Keyed on ORDER business date (§2.12). Abandoned and cancelled orders are
--           excluded -- they attached nothing to anything.
--           A week with no paid orders has no denominator and therefore no row; a rate
--           over nothing is not zero.
-- excludes: test orders (§1.1); abandoned and cancelled orders
with weeks as (
    select cast(d as date) as week_start
    from generate_series(date '2026-07-13', date '2026-08-31', interval 7 day) as t(d)
),
scoped_orders as (
    select o.order_id, o.business_date
    from orders o
    join showrooms s on s.showroom_id = o.showroom_id
    where not o.is_test
      and o.status = 'paid'
      and s.country_code = 'MY'
      and o.business_date between date '2026-07-13' and date '2026-09-06'
),
per_order as (
    select so.order_id,
           w.week_start,
           max(case when not p.is_accessory then 1 else 0 end) as has_phone,
           max(case when p.is_accessory then 1 else 0 end) as has_accessory
    from scoped_orders so
    join weeks w on so.business_date between w.week_start and w.week_start + 6
    join order_items i on i.order_id = so.order_id
    join products p on p.sku = i.sku
    group by so.order_id, w.week_start
)
select cast(week_start as varchar) as key,
       cast(sum(case when has_phone = 1 and has_accessory = 1 then 1 else 0 end) * 1.0
            / sum(has_phone) as decimal(38,12)) as value
from per_order
group by week_start
having sum(has_phone) > 0
order by key asc
