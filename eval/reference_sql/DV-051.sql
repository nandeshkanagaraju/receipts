-- qid:      DV-051
-- value:    money_minor
-- shape:    scalar
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   NOT a Kestrel metric -- median order value, per the row's `interpretation`
-- scope:    country SG
-- currency: SGD (§1.4 rule 1 -- the asker named Singapore dollars)
-- rule:     interpretation: "the 50th-percentile captured value across distinct
--           paid orders at Singapore showrooms in the window, keyed on capture
--           business date, in SGD, excluding test transactions. The glossary
--           defines the MEAN (§2.6), not the median."
--           So this is deliberately NOT average order value: a system that
--           answers §2.6 here has answered a different question. The unit of
--           observation is the same -- one distinct paid order, valued at its
--           capture, keyed on capture business date (§2.6) -- only the
--           statistic differs.
--           The median of an even-sized set falls between two orders, so the
--           result is rounded to whole minor units (§1.3).
-- excludes: test transactions (§1.1); duplicate captures
with fx as (
    select c.rate_date,
           c.currency,
           cast(c.usd_per_unit / r.usd_per_unit as decimal(38,12)) as to_reporting
    from fx_rates c
    join fx_rates r on r.rate_date = c.rate_date and r.currency = 'SGD'
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
      and s.country_code = 'SG'
      and a.business_date between date '2026-08-01' and date '2026-08-31'
),
order_value as (
    select c.order_id,
           sum(c.amount_minor * fx.to_reporting) as amount
    from captures c
    join fx on fx.currency = c.currency and fx.rate_date = c.business_date
    where c.capture_rank = 1
    group by c.order_id
)
select cast(round(median(amount)) as bigint) as value
from order_value
