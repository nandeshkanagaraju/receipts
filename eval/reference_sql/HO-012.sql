-- qid:      HO-012
-- value:    count
-- shape:    ranking
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   units sold (§2.2) by payment method
-- scope:    region IN-TN (Tamil Nadu)
-- currency: none (a count)
-- top_k:    5
-- rule:     units counts EVERY line -- phones AND accessories (§2.2, §6.1). A
--           "unit" at Kestrel is any item on an order line, so units sold is always
--           larger than phones sold. Two of the same phone on one order counts as two.
--           Only PAID orders contribute; lines on abandoned or cancelled orders are
--           excluded (§2.2). Keyed on the order business date of the order the line
--           belongs to (§2.2).
--           "By payment method" on a VOLUME metric uses the PAYING attempt (§5.3a,
--           §6.1), not §1.9's "tried" rule -- that one governs success rates only. An
--           order that tried UPI, failed, then paid by card is a card order here and
--           is not a UPI order.
--           An order captured on more than one method therefore belongs to each of
--           them, which is the rule's stated consequence rather than double counting
--           introduced here.
--           A method with no paid orders is an exact zero, not a missing row
--           (docs/M2_NOTES.md §5).
-- excludes: test orders and test attempts (§1.1); abandoned and cancelled orders;
--           the duplicate side of a duplicate capture (§4.10)
with captures as (
    select a.order_id, a.amount_minor, a.method,
           row_number() over (
               partition by a.order_id, a.amount_minor
               order by a.attempt_no, a.attempt_id
           ) as capture_rank
    from payment_attempts a
    where a.status = 'captured'
      and not a.is_test
),
paying as (
    select distinct c.order_id, c.method
    from captures c
    where c.capture_rank = 1
),
scoped_orders as (
    select o.order_id
    from orders o
    join showrooms s on s.showroom_id = o.showroom_id
    where not o.is_test
      and o.status = 'paid'
      and s.region_id = 'IN-TN'
      and o.business_date between date '2026-08-01' and date '2026-08-31'
),
spine as (
    select distinct method from payment_attempts
),
valued as (
    select p.method, sum(i.qty) as units
    from order_items i
    join scoped_orders so on so.order_id = i.order_id
    join paying p on p.order_id = i.order_id
    group by p.method
)
select sp.method as key,
       cast(coalesce(v.units, 0) as bigint) as value
from spine sp
left join valued v on v.method = sp.method
order by value desc, key asc
limit 5
