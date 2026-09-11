-- qid:      DV-021
-- value:    money_minor
-- shape:    scalar
-- window:   august_2026        -> 2026-08-01 .. 2026-08-31   (named month, as_of 2026-09-10)
-- metric:   net revenue (§2.5)
-- scope:    all countries
-- currency: USD (§1.4 rule 1 -- the asker named it)
-- rule:     captured GMV in the window MINUS refunds PROCESSED in the same
--           window (§2.5). The refunds subtracted are the ones processed in
--           August, not the refunds that eventually attach to August's
--           captures: a refund processed in September against an August capture
--           reduces September. Holding the month open until every possible
--           refund landed would mean no month ever closes.
--           Each side is converted at each amount's own date, then subtracted
--           in the reporting currency (§2.5).
-- excludes: test transactions (§1.1); pending and failed refunds; duplicate captures
with fx as (
    select c.rate_date,
           c.currency,
           cast(c.usd_per_unit / r.usd_per_unit as decimal(38,12)) as to_reporting
    from fx_rates c
    join fx_rates r on r.rate_date = c.rate_date and r.currency = 'USD'
),
captures as (
    select a.amount_minor, a.currency, a.business_date,
           row_number() over (
               partition by a.order_id, a.amount_minor
               order by a.attempt_no, a.attempt_id
           ) as capture_rank
    from payment_attempts a
    where a.status = 'captured'
      and not a.is_test
      and a.business_date between date '2026-08-01' and date '2026-08-31'
),
captured as (
    select coalesce(sum(c.amount_minor * fx.to_reporting), 0) as amount
    from captures c
    join fx on fx.currency = c.currency and fx.rate_date = c.business_date
    where c.capture_rank = 1
),
refunded as (
    select coalesce(sum(rf.amount_minor * fx.to_reporting), 0) as amount
    from refunds rf
    join orders o on o.order_id = rf.order_id
    join fx on fx.currency = rf.currency and fx.rate_date = rf.business_date
    where not o.is_test
      and rf.status = 'processed'
      and rf.business_date between date '2026-08-01' and date '2026-08-31'
)
select cast(round(captured.amount - refunded.amount) as bigint) as value
from captured, refunded
