-- qid:      HO-040
-- value:    ratio
-- shape:    ranking
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   accessory attach rate (§2.12) by payment method
-- scope:    region IN-TN (Tamil Nadu)
-- currency: none (a ratio, §2.12)
-- top_k:    5
-- rule:     attach rate is a count of ORDERS, not a split of money (§2.12, §1.7a), so
--           no handset attribution applies.
--           Numerator: paid orders with at least one phone line AND at least one
--           accessory line. Denominator: paid orders with at least one phone line
--           (§2.12).
--           "By payment method" on a metric that FILTERS A SET OF ORDERS uses the
--           PAYING attempt (§5.3a, §6.1) -- the method the money came in on -- not
--           §1.9's "tried" rule, which governs success rates only. An order that tried
--           UPI and paid by card is a card order here.
--           Both sides of the ratio are narrowed to the same orders, so the rate cannot
--           exceed 100%.
--           An order captured on more than one method belongs to each of them, which is
--           the rule's stated consequence (§5.3a).
--           Keyed on ORDER business date (§2.12).
--           A method with no paid phone orders has no denominator and therefore no cell.
-- excludes: test orders and test attempts (§1.1); abandoned and cancelled orders;
--           duplicate captures (§4.10)
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
per_order as (
    select so.order_id,
           max(case when not p.is_accessory then 1 else 0 end) as has_phone,
           max(case when p.is_accessory then 1 else 0 end) as has_accessory
    from scoped_orders so
    join order_items i on i.order_id = so.order_id
    join products p on p.sku = i.sku
    group by so.order_id
)
select pa.method as key,
       cast(sum(case when po.has_phone = 1 and po.has_accessory = 1 then 1 else 0 end) * 1.0
            / sum(po.has_phone) as decimal(38,12)) as value
from per_order po
join paying pa on pa.order_id = po.order_id
group by pa.method
having sum(po.has_phone) > 0
order by value desc, key asc
limit 5
