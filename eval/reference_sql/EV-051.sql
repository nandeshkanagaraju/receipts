-- qid:      EV-051
-- value:    money_minor
-- shape:    ranking
-- window:   july_2026          -> 2026-07-01 .. 2026-07-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   captured GMV (§2.3), by acquiring bank
-- scope:    country GB
-- currency: GBP (§1.4 rule 2 -- store_ops_uk reports in GBP)
-- top_k:    10
-- rule:     only CAPTURED money counts; an authorisation is not revenue (§4.2).
--           ACQUIRING bank -- Kestrel's bank, the one that settles the money -- not the
--           issuing bank, which is the customer's. They are different dimensions and
--           merging them reintroduces the confusion §1.9 exists to remove.
--           A value breakdown follows the money (§1.9), so each capture belongs to its own
--           attempt's acquiring bank.
-- excludes: test transactions (§1.1); duplicate captures
with fx as (
    select c.rate_date,
           c.currency,
           cast(c.usd_per_unit / r.usd_per_unit as decimal(38,12)) as to_reporting
    from fx_rates c
    join fx_rates r on r.rate_date = c.rate_date and r.currency = 'GBP'
),
captures as (
    select a.order_id, a.amount_minor, a.currency, a.business_date, a.acquiring_bank,
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
select c.acquiring_bank as key,
       cast(round(sum(c.amount_minor * fx.to_reporting)) as bigint) as value
from captures c join fx on fx.currency = c.currency and fx.rate_date = c.business_date
where c.capture_rank = 1 group by c.acquiring_bank order by value desc, key asc limit 10
