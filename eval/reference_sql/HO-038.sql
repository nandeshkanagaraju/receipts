-- qid:      HO-038
-- value:    money_minor
-- shape:    ranking
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   net revenue (§2.5) by city
-- scope:    country GB
-- currency: GBP (§1.4 rule 1 -- the asker named it)
-- top_k:    10
-- rule:     net revenue is captured GMV in the window MINUS refunds PROCESSED in the
--           same window (§2.5) -- not the refunds that eventually attach to the
--           window's captures. A refund processed in August against a July capture
--           reduces August.
--           The two sides key on DIFFERENT dates: captures on capture business date,
--           refunds on refund business date (§1.2, §2.5).
--           Net revenue can be NEGATIVE for a single city if refunds processed there
--           exceed captures. That is a real result, not an error (§2.5), and it is why
--           the ranking is by value descending rather than by magnitude.
--           Partial refunds count the amount actually refunded (§4.3).
--           A city with neither captures nor refunds is an exact zero rather than a
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
    select o.order_id, ci.name as city_name
    from orders o
    join showrooms s on s.showroom_id = o.showroom_id
    join cities ci on ci.city_id = s.city_id
    where not o.is_test
      and s.country_code = 'GB'
),
spine as (
    select distinct city_name from scoped_orders
),
captured as (
    select so.city_name, sum(c.amount_minor) as amount
    from captures c
    join scoped_orders so on so.order_id = c.order_id
    where c.capture_rank = 1
      and c.business_date between date '2026-08-01' and date '2026-08-31'
    group by so.city_name
),
refunded as (
    select so.city_name, sum(rf.amount_minor) as amount
    from refunds rf
    join scoped_orders so on so.order_id = rf.order_id
    where rf.status = 'processed'
      and rf.business_date between date '2026-08-01' and date '2026-08-31'
    group by so.city_name
)
select sp.city_name as key,
       cast(coalesce(c.amount, 0) - coalesce(r.amount, 0) as bigint) as value
from spine sp
left join captured c on c.city_name = sp.city_name
left join refunded r on r.city_name = sp.city_name
order by value desc, key asc
limit 10
