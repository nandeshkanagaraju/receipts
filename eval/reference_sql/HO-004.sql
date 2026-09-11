-- qid:      HO-004
-- value:    money_minor
-- shape:    ranking
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   captured GMV (§2.3) by colour
-- scope:    country IN
-- currency: INR (§1.4 rule 1 -- the asker named it)
-- top_k:    8
-- rule:     the colour is the ORDER'S HANDSET (§1.7a). Order-level money is
--           attributed ENTIRELY to the handset's colour -- including the case and
--           charger bought alongside it -- and is not apportioned across the lines.
--           Every order carries exactly one handset, so nothing needs allocating.
--           Captured money only (§4.2); the duplicate side of a duplicate capture is
--           counted once (§4.10).
--           A colour with no captures is an exact zero, not a missing row
--           (docs/M2_NOTES.md §5).
--           The scope is one country and one currency, so no conversion arises (§1.3).
-- excludes: test orders and test attempts (§1.1); duplicate captures
with handset as (
    select i.order_id, p.colour
    from order_items i
    join products p on p.sku = i.sku
    where not p.is_accessory
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
spine as (
    select distinct p.colour from products p where not p.is_accessory
),
valued as (
    select h.colour, sum(c.amount_minor) as amount
    from captures c
    join orders o on o.order_id = c.order_id
    join showrooms s on s.showroom_id = o.showroom_id
    join handset h on h.order_id = c.order_id
    where c.capture_rank = 1
      and not o.is_test
      and s.country_code = 'IN'
      and c.business_date between date '2026-08-01' and date '2026-08-31'
    group by h.colour
)
select sp.colour as key,
       cast(coalesce(v.amount, 0) as bigint) as value
from spine sp
left join valued v on v.colour = sp.colour
order by value desc, key asc
limit 8
