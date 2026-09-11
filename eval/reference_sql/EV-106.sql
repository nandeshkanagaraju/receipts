-- qid:      EV-106
-- value:    money_minor
-- shape:    ranking
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   captured GMV (§2.3), by country
-- scope:    all countries
-- currency: USD (§1.4 rule 1 -- the asker named it)
-- top_k:    6
-- rule:     the multi-currency trap (§4.4): raw minor units are never added across
--           currencies. Each amount converts at the daily rate for its OWN capture
--           business date (§1.3).
--           "Rank the six countries" names the quantity to rank on -- captured GMV -- so
--           it is not the undefined word "best" (§5.5).
-- excludes: test transactions (§1.1); duplicate captures
with fx as (
    select c.rate_date,
           c.currency,
           cast(c.usd_per_unit / r.usd_per_unit as decimal(38,12)) as to_reporting
    from fx_rates c
    join fx_rates r on r.rate_date = c.rate_date and r.currency = 'USD'
),
captures as (
    select a.order_id, a.amount_minor, a.currency, a.business_date, s.country_code,
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
      and a.business_date between date '2026-08-01' and date '2026-08-31'
)
select c.country_code as key,
       cast(round(sum(c.amount_minor * fx.to_reporting)) as bigint) as value
from captures c join fx on fx.currency = c.currency and fx.rate_date = c.business_date
where c.capture_rank = 1 group by c.country_code order by value desc, key asc limit 6
