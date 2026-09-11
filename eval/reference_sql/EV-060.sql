-- qid:      EV-060
-- value:    money_minor
-- shape:    scalar
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   average order value (§2.6) for EMI-paid orders
-- scope:    region IN-TN (Tamil Nadu), EMI-paid orders only
-- currency: INR (§1.4 rule 2 -- rm_tamil_nadu reports in INR)
-- rule:     "EMI orders" means orders whose CAPTURED attempt used EMI (§5.3a) -- the
--           method the money actually came in on, not the tried rule of §1.9.
--           AOV is captured GMV over distinct PAID orders, both keyed on capture business
--           date (§2.6).
--           The order value is the FULL order value, not the monthly instalment (§4.9):
--           using the instalment would divide a twelve-month order by its tenure.
-- excludes: test transactions (§1.1); duplicate captures
with fx as (
    select c.rate_date,
           c.currency,
           cast(c.usd_per_unit / r.usd_per_unit as decimal(38,12)) as to_reporting
    from fx_rates c
    join fx_rates r on r.rate_date = c.rate_date and r.currency = 'INR'
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
      and s.region_id = 'IN-TN' and a.method = 'emi'
      and a.business_date between date '2026-08-01' and date '2026-08-31'
)
select cast(round(
           sum(c.amount_minor * fx.to_reporting) / count(distinct c.order_id)
       ) as bigint) as value
from captures c join fx on fx.currency = c.currency and fx.rate_date = c.business_date
where c.capture_rank = 1
