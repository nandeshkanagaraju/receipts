-- qid:      DV-045
-- value:    money_minor
-- shape:    series
-- window:   last_8_weeks       -> 2026-07-13 .. 2026-09-06   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   captured GMV (§2.3), weekly
-- scope:    country GB
-- currency: GBP (§1.4 rule 2 -- store_ops_uk reports in GBP)
-- rule:     "last 8 weeks" is EIGHT COMPLETE Monday-Sunday weeks (§1.6a). The
--           current partial week is EXCLUDED, not counted as one of the eight --
--           counting it would make the most recent point look like a collapse.
--           A series is matched by time key, not by rank (ADR-009), and the key
--           is each week's Monday.
-- excludes: test transactions (§1.1); duplicate captures
with fx as (
    select c.rate_date,
           c.currency,
           cast(c.usd_per_unit / r.usd_per_unit as decimal(38,12)) as to_reporting
    from fx_rates c
    join fx_rates r on r.rate_date = c.rate_date and r.currency = 'GBP'
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
      and s.country_code = 'GB'
      and a.business_date between date '2026-07-13' and date '2026-09-06'
)
select cast(cast(date_trunc('week', c.business_date) as date) as varchar) as key,
       cast(round(sum(c.amount_minor * fx.to_reporting)) as bigint) as value
from captures c
join fx on fx.currency = c.currency and fx.rate_date = c.business_date
where c.capture_rank = 1
group by key
order by key asc
