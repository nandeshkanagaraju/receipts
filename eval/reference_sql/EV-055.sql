-- qid:      EV-055
-- value:    money_minor
-- shape:    scalar
-- window:   july_2026          -> 2026-07-01 .. 2026-07-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   unsettled amount (§2.14)
-- scope:    all countries
-- currency: USD (§1.4 rule 1 -- the asker named it)
-- capability: finance (§2.14)
-- rule:     A SNAPSHOT, NOT A FLOW (§2.14). "At the end of July" means captures on or
--           before 2026-07-31 that had NOT settled by 2026-07-31. It is NOT "captures
--           during July that are still unsettled": there is no lower bound, and a payment
--           captured four months earlier and still unsettled is included -- unsettled cash
--           does not age out.
--           Each amount converts at the rate for its OWN capture business date, not the
--           rate on the snapshot date, so this reconciles with captured GMV, of which it
--           is a subset valued identically (§2.14).
--           Read together with settlement lag (§2.13): the lag average excludes exactly
--           the captures this figure counts.
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
    where a.status = 'captured' and not a.is_test
      and a.business_date <= date '2026-07-31'
),
settled_by_d as (
    select si.attempt_id
    from settlement_items si
    join settlements st on st.settlement_id = si.settlement_id
    where st.settled_on <= date '2026-07-31'
)
select cast(round(coalesce(sum(c.amount_minor * fx.to_reporting), 0)) as bigint) as value
from captures c join fx on fx.currency = c.currency and fx.rate_date = c.business_date
where c.capture_rank = 1 and c.attempt_id not in (select attempt_id from settled_by_d)
