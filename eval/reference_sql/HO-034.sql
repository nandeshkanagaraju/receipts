-- qid:      HO-034
-- value:    ratio
-- shape:    ranking
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   refund rate (§2.7) by payment method
-- scope:    region IN-TN (Tamil Nadu)
-- currency: none (a ratio has no currency, §2.7)
-- top_k:    5
-- rule:     refund rate is VALUE-based, not count-based (§2.7, §6.1): refunded amount
--           over captured GMV. "What share of orders were refunded" is a different
--           number and is not what refund rate means at Kestrel.
--           Each side keys on its OWN date (§2.7): refunds on refund business date,
--           captures on capture business date. The two sides therefore do not describe
--           the same orders, and for a short window a rate can exceed 100% if a large
--           refund lands in a quiet period. That is expected.
--           "By payment method" on a VALUE metric uses the PAYING attempt (§5.3a,
--           §6.1), not §1.9's "tried" rule. Both sides are narrowed to the SAME set of
--           orders: leaving the refund side unnarrowed would put every refund in the
--           region into every method's numerator and push per-method rates above 100%.
--           Partial refunds count the amount actually refunded (§4.3).
--           A method with no captured GMV has no denominator and therefore no cell --
--           a rate over nothing is not zero.
--           The scope is one region and one currency, so no conversion arises (§1.3).
-- excludes: test orders and test attempts (§1.1); pending and failed refunds (§2.4);
--           duplicate captures (§4.10)
with captures as (
    select a.order_id, a.amount_minor, a.business_date, a.method,
           row_number() over (
               partition by a.order_id, a.amount_minor
               order by a.attempt_no, a.attempt_id
           ) as capture_rank
    from payment_attempts a
    where a.status = 'captured'
      and not a.is_test
),
scoped_orders as (
    select o.order_id
    from orders o
    join showrooms s on s.showroom_id = o.showroom_id
    where not o.is_test
      and s.region_id = 'IN-TN'
),
paying as (
    select distinct c.order_id, c.method
    from captures c
    join scoped_orders so on so.order_id = c.order_id
    where c.capture_rank = 1
),
captured as (
    select c.method, sum(c.amount_minor) as gmv_minor
    from captures c
    join scoped_orders so on so.order_id = c.order_id
    where c.capture_rank = 1
      and c.business_date between date '2026-08-01' and date '2026-08-31'
    group by c.method
),
refunded as (
    select p.method, sum(rf.amount_minor) as refund_minor
    from refunds rf
    join scoped_orders so on so.order_id = rf.order_id
    join paying p on p.order_id = rf.order_id
    where rf.status = 'processed'
      and rf.business_date between date '2026-08-01' and date '2026-08-31'
    group by p.method
)
select c.method as key,
       cast(coalesce(r.refund_minor, 0) * 1.0 / c.gmv_minor as decimal(38,12)) as value
from captured c
left join refunded r on r.method = c.method
where c.gmv_minor > 0
order by value desc, key asc
limit 5
