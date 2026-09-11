-- qid:      HO-015
-- value:    ratio
-- shape:    scalar
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (on ATTEMPT business date)
-- metric:   attempts per paid order -- NOT a glossary metric; the row's
--           `interpretation` governs (ADR-009)
-- scope:    country GB
-- currency: none (a ratio)
-- rule:     the row carries an `interpretation` and that sentence governs the
--           numerator, the denominator and the date key.
--           Numerator: non-test attempts, of ANY outcome, on orders that reached PAID
--           status, with the ATTEMPT's business date in the window.
--           Denominator: the count of those distinct paid orders.
--           The interpretation keys the window on ATTEMPT business date, so the
--           order's own date is not constrained -- an order placed in July whose
--           attempts fall in August contributes to August.
--           This is deliberately NOT DV-011, which divides by all orders with at least
--           one attempt, paid or not. Restricting the denominator to paid orders makes
--           the figure larger: the orders that never succeeded are the ones carrying
--           the most failed attempts (§4.1).
--           "Reached paid status" is read as §2.8 reads it -- at least one CAPTURED
--           attempt -- not as a trust of the order's status column, and since ADR-014
--           an `authorized` attempt is not a capture (§4.2).
-- excludes: test orders and test attempts (§1.1)
with paid_orders as (
    select distinct a.order_id
    from payment_attempts a
    join orders o on o.order_id = a.order_id
    join showrooms s on s.showroom_id = o.showroom_id
    where a.status = 'captured'
      and not a.is_test
      and not o.is_test
      and s.country_code = 'GB'
),
windowed as (
    select a.order_id
    from payment_attempts a
    join paid_orders po on po.order_id = a.order_id
    where not a.is_test
      and a.business_date between date '2026-08-01' and date '2026-08-31'
)
select cast(count(*) * 1.0 / count(distinct order_id) as decimal(38,12)) as value
from windowed
order by value
