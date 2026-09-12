-- qid:      HO-011
-- value:    money_minor
-- shape:    ranking
-- window:   july_2026          -> 2026-07-01 .. 2026-07-31
-- metric:   net revenue (§2.5) by channel
-- scope:    country AE
-- currency: AED (§1.4 rule 1 -- the asker named it)
-- top_k:    2
-- rule:     net revenue is captured GMV in the window MINUS refunds PROCESSED in the
--           same window (§2.5). The refunds subtracted are the ones processed in the
--           window, not the refunds that eventually attach to the window's captures:
--           a refund processed in July against a June capture reduces July. The
--           alternative would hold every month open until the last possible refund
--           landed, so no month would ever close.
--           The two sides key on DIFFERENT dates -- captures on capture business date,
--           refunds on refund business date (§1.2, §2.5) -- and that is the
--           definition, not a mismatch to fix.
--           Partial refunds count the amount actually refunded (§4.3).
--           Net revenue can be negative for a single channel if refunds processed
--           there exceed captures. That is a real result, not an error (§2.5).
--           A channel with neither captures nor refunds is an exact zero rather than a
--           missing row (docs/M2_NOTES.md §5).
--           The scope is one country and one currency, so no conversion arises (§1.3).
-- excludes: test orders and test attempts (§1.1); pending and failed refunds (§2.4);
--           duplicate captures (§4.10)
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
    select o.order_id, o.channel
    from orders o
    join showrooms s on s.showroom_id = o.showroom_id
    where not o.is_test
      and s.country_code = 'AE'
),
spine as (
    select distinct channel from scoped_orders
),
captured as (
    select so.channel, sum(c.amount_minor) as amount
    from captures c
    join scoped_orders so on so.order_id = c.order_id
    where c.capture_rank = 1
      and c.business_date between date '2026-07-01' and date '2026-07-31'
    group by so.channel
),
refunded as (
    select so.channel, sum(rf.amount_minor) as amount
    from refunds rf
    join scoped_orders so on so.order_id = rf.order_id
    where rf.status = 'processed'
      and rf.business_date between date '2026-07-01' and date '2026-07-31'
    group by so.channel
)
select sp.channel as key,
       cast(coalesce(c.amount, 0) - coalesce(r.amount, 0) as bigint) as value
from spine sp
left join captured c on c.channel = sp.channel
left join refunded r on r.channel = sp.channel
order by value desc, key asc
limit 2
