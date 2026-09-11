-- qid:      EV-076
-- value:    money_minor
-- shape:    scalar
-- window:   july_2026          -> 2026-07-01 .. 2026-07-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   net revenue (§2.5) for pay-later orders
-- scope:    country GB, pay-later-paid orders only
-- currency: GBP (§1.4 rule 1 -- "in pounds")
-- rule:     "pay-later orders" means orders whose CAPTURED attempt used pay_later
--           (§5.3a), not orders that merely tried it -- the tried rule of §1.9 governs
--           success rates only.
--           Net revenue is captured GMV minus refunds PROCESSED in the same window (§2.5);
--           the refund is attributed to the same order's pay-later capture so both sides
--           describe the same order set.
--           Net revenue can be negative for a narrow slice; that is a real result (§2.5).
-- excludes: test transactions (§1.1); pending and failed refunds; duplicate captures
with fx as (
    select c.rate_date,
           c.currency,
           cast(c.usd_per_unit / r.usd_per_unit as decimal(38,12)) as to_reporting
    from fx_rates c
    join fx_rates r on r.rate_date = c.rate_date and r.currency = 'GBP'
),
captures as (
    select a.order_id, a.amount_minor, a.currency, a.business_date,
           row_number() over (
               partition by a.order_id, a.amount_minor
               order by a.attempt_no, a.attempt_id
           ) as capture_rank
    from payment_attempts a
    join orders o on o.order_id = a.order_id
    join showrooms s on s.showroom_id = o.showroom_id
    where a.status = 'captured'
      and not a.is_test
      and not o.is_test
      and s.country_code = 'GB' and a.method = 'pay_later'
      
),
captured as (
    select coalesce(sum(c.amount_minor * fx.to_reporting), 0) as amount
    from captures c join fx on fx.currency = c.currency and fx.rate_date = c.business_date
    where c.capture_rank = 1
      and c.business_date between date '2026-07-01' and date '2026-07-31'
),
refunded as (
    select coalesce(sum(rf.amount_minor * fx.to_reporting), 0) as amount
    from refunds rf
    join captures c on c.order_id = rf.order_id and c.capture_rank = 1
    join fx on fx.currency = rf.currency and fx.rate_date = rf.business_date
    where rf.status = 'processed'
      and rf.business_date between date '2026-07-01' and date '2026-07-31'
)
select cast(round(captured.amount - refunded.amount) as bigint) as value
from captured, refunded
