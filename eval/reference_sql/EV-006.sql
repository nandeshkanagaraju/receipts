-- qid:      EV-006
-- value:    money_minor
-- shape:    ranking
-- window:   july_2026          -> 2026-07-01 .. 2026-07-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   average order value (§2.6), by city
-- scope:    country GB
-- currency: GBP (§1.4 rule 2 -- store_ops_uk reports in GBP)
-- top_k:    10
-- rule:     captured GMV divided by the count of distinct PAID orders that produced it
--           (§2.6). Abandoned and cancelled orders are not in the denominator: they
--           contributed nothing to the numerator and including them would understate the
--           average.
--           BOTH sides key on capture business date so they describe the same order set.
--           For EMI orders the value is the full order value, not the instalment (§4.9).
-- excludes: test transactions (§1.1); duplicate captures
with fx as (
    select c.rate_date,
           c.currency,
           cast(c.usd_per_unit / r.usd_per_unit as decimal(38,12)) as to_reporting
    from fx_rates c
    join fx_rates r on r.rate_date = c.rate_date and r.currency = 'GBP'
),
captures as (
    select a.order_id, a.amount_minor, a.currency, a.business_date, s.city_id,
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
      and s.country_code = 'GB'
      and a.business_date between date '2026-07-01' and date '2026-07-31'
)
select ci.name as key,
       cast(round(
           sum(c.amount_minor * fx.to_reporting) / count(distinct c.order_id)
       ) as bigint) as value
from captures c
join fx on fx.currency = c.currency and fx.rate_date = c.business_date
join cities ci on ci.city_id = c.city_id
where c.capture_rank = 1
group by ci.name
order by value desc, key asc
limit 10
