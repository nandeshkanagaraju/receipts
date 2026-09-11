-- qid:      EV-029
-- value:    ratio
-- shape:    scalar
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   NOT a Kestrel metric -- items per order, per the row's `interpretation`
-- scope:    country SG
-- currency: none
-- rule:     interpretation: "total quantity across order lines of non-test paid orders
--           at Singapore showrooms in the window, divided by the count of those orders,
--           keyed on order business date."
--           Basket size in ITEMS is not a Kestrel metric; average order value (§2.6) is in
--           MONEY, and answering that here answers a different question.
--           Quantity counts every line -- accessories included, as units does (§2.2).
-- excludes: test orders (§1.1); abandoned and cancelled orders
with per_order as (
    select o.order_id, sum(i.qty) as items
    from orders o
    join order_items i on i.order_id = o.order_id
    join showrooms s on s.showroom_id = o.showroom_id
    where not o.is_test and o.status = 'paid' and s.country_code = 'SG'
      and o.business_date between date '2026-08-01' and date '2026-08-31'
    group by o.order_id
)
select cast(sum(items) * 1.0 / count(*) as decimal(38,12)) as value from per_order
order by value
