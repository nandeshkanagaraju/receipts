-- qid:      EV-015
-- value:    money_minor
-- shape:    series
-- window:   last_7_days        -> 2026-09-03 .. 2026-09-09   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   captured GMV (§2.3), daily
-- scope:    city Chennai
-- currency: INR (§1.4 rule 1 -- "in rupees")
-- rule:     a SERIES is matched by TIME KEY, not by rank (ADR-009): a rank comparison
--           would pass a result whose days were right but misordered, which for a series
--           is the entire answer. It carries no top_k.
--           "The last 7 days" is the seven days ending YESTERDAY -- the reporting day is
--           excluded because it is not over, and a partial day understates its own figure
--           (§1.6a). This is a different window from "last week" (§1.6).
--           Each day is the showroom's own local business date (§1.7, §4.5).
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
    join cities ci on ci.city_id = s.city_id
    where a.status = 'captured'
      and not a.is_test
      and not o.is_test
      and ci.name = 'Chennai'
      and a.business_date between date '2026-09-03' and date '2026-09-09'
)
select cast(c.business_date as varchar) as key,
       cast(round(sum(c.amount_minor * fx.to_reporting)) as bigint) as value
from captures c
join fx on fx.currency = c.currency and fx.rate_date = c.business_date
where c.capture_rank = 1
group by c.business_date order by key asc
