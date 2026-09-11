-- qid:      EV-127
-- value:    money_minor
-- shape:    ranking
-- window:   fy2027_q1          -> 2026-04-01 .. 2026-06-30   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   captured GMV (§2.3), by country
-- scope:    all countries
-- currency: USD (§1.4 rule 1 -- the asker named it)
-- top_k:    6
-- rule:     the fiscal-calendar trap (§4.6). The fiscal year starts 1 APRIL and is named
--           for the year it ENDS in, so FY2027 runs 2026-04-01 to 2027-03-31 and its Q1 is
--           APRIL-JUNE 2026 (§1.5).
--           Compare EV-023, the same quarter one fiscal year earlier. A calendar reading
--           would give January-March and a materially different number, which is why an
--           unqualified "Q1" must be clarified (§4.6) -- this question is explicit and is
--           answered directly.
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
      and a.business_date between date '2026-04-01' and date '2026-06-30'
)
select c.country_code as key,
       cast(round(sum(c.amount_minor * fx.to_reporting)) as bigint) as value
from captures c join fx on fx.currency = c.currency and fx.rate_date = c.business_date
where c.capture_rank = 1 group by c.country_code order by value desc, key asc limit 6
