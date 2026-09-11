-- qid:      DV-003
-- value:    money_minor
-- shape:    scalar
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   captured GMV (§2.3)
-- scope:    all countries
-- currency: USD (§1.4 rule 1 -- the asker named it)
-- rule:     captured money only, never authorised (§4.2). Each amount is
--           converted at the daily rate for its OWN capture business date
--           (§1.3), not one rate for the window. The duplicate side of a
--           duplicate capture is counted once (§4.10).
-- excludes: test attempts (§1.1); failed attempts; duplicate captures
with fx as (
    select c.rate_date,
           c.currency,
           cast(c.usd_per_unit / r.usd_per_unit as decimal(38,12)) as to_reporting
    from fx_rates c
    join fx_rates r on r.rate_date = c.rate_date and r.currency = 'USD'
),
captures as (
    select a.attempt_id, a.amount_minor, a.currency, a.business_date,
           row_number() over (
               partition by a.order_id, a.amount_minor
               order by a.attempt_no, a.attempt_id
           ) as capture_rank
    from payment_attempts a
    where a.status = 'captured'
      and not a.is_test
      and a.business_date between date '2026-08-01' and date '2026-08-31'
)
select cast(round(sum(c.amount_minor * fx.to_reporting)) as bigint) as value
from captures c
join fx on fx.currency = c.currency and fx.rate_date = c.business_date
where c.capture_rank = 1
