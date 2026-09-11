-- qid:      EV-117
-- value:    ratio
-- shape:    ranking
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   NOT a governed dimension -- EMI share (§2.11) by tenure
-- scope:    country IN
-- currency: INR (§1.4 rule 2 via India's single currency); both sides converted before dividing
-- top_k:    6
-- rule:     interpretation: "captured non-test value on orders whose captured attempt
--           was EMI, grouped by emi_tenure_months, divided by total captured non-test
--           value at Indian showrooms in the window, keyed on capture business date.
--           Tenure is not a governed dimension."
--           THE DENOMINATOR IS TOTAL CAPTURED VALUE, NOT EMI VALUE. So these shares sum to
--           the overall EMI share (§2.11), not to 100% -- the same shape of error §2.10
--           warns about for failure reasons. A set of per-tenure figures summing to 100%
--           has been computed against EMI value instead.
--           The value is the FULL ORDER VALUE, never the monthly instalment (§4.9) -- which
--           is precisely the trap tenure invites: a 12-month order is not one twelfth.
-- excludes: test transactions (§1.1); duplicate captures
with fx as (
    select c.rate_date,
           c.currency,
           cast(c.usd_per_unit / r.usd_per_unit as decimal(38,12)) as to_reporting
    from fx_rates c
    join fx_rates r on r.rate_date = c.rate_date and r.currency = 'INR'
),
captures as (
    select a.order_id, a.amount_minor, a.currency, a.business_date, a.method, a.emi_tenure_months,
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
      and s.country_code = 'IN'
      and a.business_date between date '2026-08-01' and date '2026-08-31'
),
valued as (
    select c.method, c.emi_tenure_months,
           c.amount_minor * fx.to_reporting as amount
    from captures c join fx on fx.currency = c.currency and fx.rate_date = c.business_date
    where c.capture_rank = 1
)
select emi_tenure_months as key,
       cast(sum(amount) / (select sum(amount) from valued) as decimal(38,12)) as value
from valued where method = 'emi'
group by emi_tenure_months order by value desc, key asc limit 6
