-- qid:      DV-004
-- value:    money_minor
-- shape:    scalar
-- window:   last_week          -> 2026-08-31 .. 2026-09-06   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   captured GMV (§2.3)
-- scope:    country GB
-- currency: GBP (§1.4 rule 2 -- store_ops_uk reports in GBP)
-- rule:     "collect" means captured (§5.1), and "actually collect" is the
--           authorised-versus-captured trap (§4.2): an authorisation reserves
--           funds, a capture takes them, and only the capture is money.
--           "Last week" is the most recent COMPLETE Monday-Sunday week, not
--           the last seven days (§1.6).
-- excludes: test attempts (§1.1); failed attempts; duplicate captures
with fx as (
    select c.rate_date,
           c.currency,
           cast(c.usd_per_unit / r.usd_per_unit as decimal(38,12)) as to_reporting
    from fx_rates c
    join fx_rates r on r.rate_date = c.rate_date and r.currency = 'GBP'
),
captures as (
    select a.attempt_id, a.amount_minor, a.currency, a.business_date,
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
      and a.business_date between date '2026-08-31' and date '2026-09-06'
)
select cast(round(sum(c.amount_minor * fx.to_reporting)) as bigint) as value
from captures c
join fx on fx.currency = c.currency and fx.rate_date = c.business_date
where c.capture_rank = 1
