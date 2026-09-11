-- qid:      EV-063
-- value:    money_minor
-- shape:    compare
-- window:   this_month_to_date -> 2026-09-01 .. 2026-09-09   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   captured GMV (§2.3)
-- scope:    country IN
-- currency: INR (§1.4 rule 1 -- "in rupees")
-- rule:     EQUAL-LENGTH WINDOWS (§1.6a, SDD §9.1 rule 5): 1-9 September against 1-9
--           August, nine days each. NOT the whole of August -- comparing nine days against
--           thirty-one would show a collapse every month as a calendar artefact.
--           Both values are returned, keyed `current` and `comparison` (ADR-009).
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
    where a.status = 'captured' and not a.is_test and not o.is_test
      and s.country_code = 'IN'
      and (a.business_date between date '2026-09-01' and date '2026-09-09'
        or a.business_date between date '2026-08-01' and date '2026-08-09')
)
select case when c.business_date >= date '2026-09-01' then 'current' else 'comparison' end as key,
       cast(round(sum(c.amount_minor * fx.to_reporting)) as bigint) as value
from captures c join fx on fx.currency = c.currency and fx.rate_date = c.business_date
where c.capture_rank = 1 group by key order by key asc
