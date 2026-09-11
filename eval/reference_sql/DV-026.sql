-- qid:      DV-026
-- value:    money_minor
-- shape:    scalar
-- window:   august_2026        -> snapshot at 2026-08-31, the window's END (GLOSSARY §2.14)
--           §2.14 is a SNAPSHOT, so only the upper bound is used: captures on
--           or before it, unsettled by it. There is no lower bound.
-- metric:   unsettled amount (§2.14)
-- scope:    all countries
-- currency: USD (§1.4 rule 1 -- the asker named it)
-- capability: finance (§2.14)
-- rule:     THIS IS A SNAPSHOT, NOT A FLOW (§2.14). "Unsettled at the end of
--           August" means captures on or before 31 August that had NOT settled
--           by 31 August. It is NOT "captures during August that are still
--           unsettled": there is no lower bound, and a payment captured four
--           months earlier and still unsettled is included -- unsettled cash
--           does not age out.
--           Each amount is converted at the daily rate for its OWN capture
--           business date, not the rate on the snapshot date, so this
--           reconciles with captured GMV, of which it is a subset (§2.14).
-- excludes: test transactions (§1.1); duplicate captures
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
      and a.business_date <= date '2026-08-31'
),
settled_by_d as (
    select si.attempt_id
    from settlement_items si
    join settlements st on st.settlement_id = si.settlement_id
    where st.settled_on <= date '2026-08-31'
)
select cast(round(coalesce(sum(c.amount_minor * fx.to_reporting), 0)) as bigint) as value
from captures c
join fx on fx.currency = c.currency and fx.rate_date = c.business_date
where c.capture_rank = 1
  and c.attempt_id not in (select attempt_id from settled_by_d)
