-- qid:      HO-003
-- value:    ratio
-- shape:    ranking
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   refund rate (§2.7) by storage size, for one handset model
-- scope:    region IN-TN (Tamil Nadu), handset model 'Kestrel Onyx'
-- currency: none (a ratio has no currency, §2.7)
-- top_k:    5
-- rule:     refund rate is VALUE-based, not count-based (§2.7, §6.1): refunded amount
--           over captured GMV, NOT the share of orders that were refunded.
--           Each side is keyed on its OWN date (§2.7): refunds on refund business
--           date, captures on capture business date. The two sides therefore do not
--           describe the same orders, and that is the definition rather than a defect.
--           The storage size is the ORDER'S HANDSET (§1.7a): order-level money is
--           attributed entirely to the handset, and every order carries exactly one.
--           Accessory lines contribute nothing to the split.
--           VOLUME FLOOR, stated in the question: only storage sizes with at least
--           100 paid orders in the window. "Paid orders" is §2.6's denominator --
--           distinct orders with at least one captured payment, on capture business
--           date. Without the floor a rate ranking is decided by whichever cell has
--           three orders and one refund (eval/questions/README.md rule 10).
--           The scope is one region and one currency, so no conversion arises (§1.3).
-- excludes: test orders and test attempts (§1.1); pending and failed refunds (§2.4);
--           the duplicate side of a duplicate capture (§2.3, §4.10)
with handset as (
    select i.order_id, p.storage_gb
    from order_items i
    join products p on p.sku = i.sku
    where not p.is_accessory
      and p.model_name = 'Kestrel Onyx'
),
scope as (
    select o.order_id, h.storage_gb
    from orders o
    join showrooms s on s.showroom_id = o.showroom_id
    join handset h on h.order_id = o.order_id
    where not o.is_test
      and s.region_id = 'IN-TN'
),
captures as (
    select a.order_id, a.amount_minor, a.business_date,
           row_number() over (
               partition by a.order_id, a.amount_minor
               order by a.attempt_no, a.attempt_id
           ) as capture_rank
    from payment_attempts a
    where a.status = 'captured'
      and not a.is_test
),
captured as (
    select sc.storage_gb,
           sum(c.amount_minor) as gmv_minor,
           count(distinct c.order_id) as paid_orders
    from captures c
    join scope sc on sc.order_id = c.order_id
    where c.capture_rank = 1
      and c.business_date between date '2026-08-01' and date '2026-08-31'
    group by sc.storage_gb
),
refunded as (
    select sc.storage_gb, sum(rf.amount_minor) as refund_minor
    from refunds rf
    join scope sc on sc.order_id = rf.order_id
    where rf.status = 'processed'
      and rf.business_date between date '2026-08-01' and date '2026-08-31'
    group by sc.storage_gb
)
select cast(c.storage_gb as varchar) as key,
       cast(coalesce(r.refund_minor, 0) * 1.0 / c.gmv_minor as decimal(38,12)) as value
from captured c
left join refunded r on r.storage_gb = c.storage_gb
where c.paid_orders >= 100
  and c.gmv_minor > 0
order by value desc, key asc
limit 5
