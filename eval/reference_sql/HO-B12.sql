-- qid:      HO-B12
-- value:    count
-- shape:    scalar
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   a count of method-qualified orders -- NOT a glossary metric; the row's
--           `interpretation` governs (ADR-009)
-- scope:    country GB, orders paid by pay-later
-- currency: none (a count)
-- rule:     the row carries an `interpretation` because §5.3a defines what a
--           method-qualified order IS but the glossary defines no count of them.
--           "Pay-later orders" means orders whose CAPTURED attempt used pay-later
--           (§5.3a, §6.1) -- the method the money actually came in on. This is
--           deliberately NOT §1.9's "tried" rule, which governs success rates only: an
--           order that tried pay-later, failed, and paid by card is not a pay-later
--           order here.
--           An order never captured has no paying method and is in no method-qualified
--           set at all (§5.3a), so "placed" cannot be read as "attempted".
--           "Placed ... last month" keys the window on the ORDER business date, while
--           the method qualification comes from the capture; the two are different dates
--           on purpose (§1.2).
--           Distinct orders are counted, so an order with two pay-later captures counts
--           once.
-- excludes: test orders and test attempts (§1.1); duplicate captures (§4.10)
with captures as (
    select a.order_id, a.attempt_id, a.amount_minor, a.currency, a.business_date,
           a.method, a.acquiring_bank,
           row_number() over (
               partition by a.order_id, a.amount_minor
               order by a.attempt_no, a.attempt_id
           ) as capture_rank
    from payment_attempts a
    where a.status = 'captured'
      and not a.is_test
),
pay_later as (
    select distinct c.order_id
    from captures c
    where c.capture_rank = 1
      and c.method = 'pay_later'
)
select count(distinct o.order_id) as value
from orders o
join showrooms s on s.showroom_id = o.showroom_id
join pay_later pl on pl.order_id = o.order_id
where not o.is_test
  and s.country_code = 'GB'
  and o.business_date between date '2026-08-01' and date '2026-08-31'
order by value
