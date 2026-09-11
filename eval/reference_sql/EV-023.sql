-- qid:      EV-023
-- value:    money_minor
-- shape:    scalar
-- window:   fy2026_q1          -> 2025-04-01 .. 2025-06-30   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   captured GMV (§2.3)
-- scope:    all countries
-- currency: USD (§1.4 rule 1 -- the asker named it)
-- rule:     the fiscal-calendar trap (§4.6). Kestrel's fiscal year starts on 1 APRIL and
--           is named for the year it ENDS in, so FY2026 runs 2025-04-01 to 2026-03-31 and
--           its Q1 is APRIL-JUNE 2025 (§1.5).
--           "Q2" or "this quarter" on its own would be AMBIGUOUS and must be clarified,
--           because both the fiscal and calendar readings are defensible and the numbers
--           differ materially (§4.6). This question is NOT ambiguous: it says "fiscal
--           Q1 of FY2026" explicitly, and an explicit reference is answered directly.
-- excludes: test transactions (§1.1); duplicate captures
with fx as (
    select c.rate_date,
           c.currency,
           cast(c.usd_per_unit / r.usd_per_unit as decimal(38,12)) as to_reporting
    from fx_rates c
    join fx_rates r on r.rate_date = c.rate_date and r.currency = 'USD'
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
      and 1 = 1
      and a.business_date between date '2025-04-01' and date '2025-06-30'
)
select cast(round(sum(c.amount_minor * fx.to_reporting)) as bigint) as value
from captures c join fx on fx.currency = c.currency and fx.rate_date = c.business_date
where c.capture_rank = 1
