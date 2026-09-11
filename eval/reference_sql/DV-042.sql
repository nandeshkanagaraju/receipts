-- qid:      DV-042
-- value:    money_minor
-- shape:    compare
-- window:   last_month         -> 2026-08-01 .. 2026-08-31 against 2025-08-01 .. 2025-08-31
--           (the comparison window is the same month one year earlier, §1.6a)
-- metric:   captured GMV (§2.3), by country
-- scope:    all countries
-- currency: USD (§1.4 rule 1 -- the asker named it)
-- top_k:    6
-- rule:     the multi-currency trap (§4.4). Kestrel takes money in six
--           currencies stored in minor units; summing the raw stored numbers
--           across countries produces a figure that is not money in any
--           currency, and it looks entirely plausible. Every amount is
--           converted at the daily rate for its OWN capture business date
--           (§1.3) -- not one rate for the window, and not today's rate.
--           The windows are equal-length calendar months (§1.6a).
--           Keys are `<country>|current` and `<country>|comparison` so both
--           periods must be present per country (ADR-009).
-- excludes: test transactions (§1.1); duplicate captures
with fx as (
    select c.rate_date,
           c.currency,
           cast(c.usd_per_unit / r.usd_per_unit as decimal(38,12)) as to_reporting
    from fx_rates c
    join fx_rates r on r.rate_date = c.rate_date and r.currency = 'USD'
),
captures as (
    select s.country_code, a.amount_minor, a.currency, a.business_date, a.order_id,
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
      and (a.business_date between date '2026-08-01' and date '2026-08-31'
        or a.business_date between date '2025-08-01' and date '2025-08-31')
)
select c.country_code || '|' ||
       case when c.business_date >= date '2026-01-01' then 'current' else 'comparison' end as key,
       cast(round(sum(c.amount_minor * fx.to_reporting)) as bigint) as value
from captures c
join fx on fx.currency = c.currency and fx.rate_date = c.business_date
where c.capture_rank = 1
group by key
order by key asc
