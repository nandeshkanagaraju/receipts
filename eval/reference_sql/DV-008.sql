-- qid:      DV-008
-- value:    ratio
-- shape:    scalar
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   EMI share (§2.11)
-- scope:    country IN
-- currency: INR for both sides before dividing (§1.4 rule 3 -- India is one currency)
-- rule:     share of captured VALUE paid by instalments. The value counted is
--           the full order value, never the monthly instalment (§4.9). A value
--           metric broken down by method follows the money (§1.9): the amount
--           belongs to the attempt that carried it, so the numerator is
--           captures whose own method is EMI.
-- excludes: test transactions (§1.1); failed attempts; duplicate captures
with fx as (
    select c.rate_date,
           c.currency,
           cast(c.usd_per_unit / r.usd_per_unit as decimal(38,12)) as to_reporting
    from fx_rates c
    join fx_rates r on r.rate_date = c.rate_date and r.currency = 'INR'
),
captures as (
    select a.method, a.amount_minor, a.currency, a.business_date,
           row_number() over (
               partition by a.order_id, a.amount_minor
               order by a.attempt_no, a.attempt_id
           ) as capture_rank
    from payment_attempts a
    join orders o on o.order_id = a.order_id
    join showrooms s on s.showroom_id = o.showroom_id
    where a.status = 'captured'
      and not a.is_test
      and s.country_code = 'IN'
      and a.business_date between date '2026-08-01' and date '2026-08-31'
)
select cast(
           sum(case when c.method = 'emi' then c.amount_minor * fx.to_reporting else 0 end)
           / sum(c.amount_minor * fx.to_reporting)
       as decimal(38,12)) as value
from captures c
join fx on fx.currency = c.currency and fx.rate_date = c.business_date
where c.capture_rank = 1
