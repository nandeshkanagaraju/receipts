-- qid:      EV-021
-- value:    money_minor
-- shape:    ranking
-- window:   july_2026          -> 2026-07-01 .. 2026-07-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   captured GMV (§2.3), by payment method
-- scope:    country IN
-- currency: INR (§1.4 rule 1 -- "in rupees")
-- top_k:    5
-- rule:     a VALUE metric broken down by method follows the money (§1.9): each amount
--           is attributed to the attempt that actually carried it -- the capture -- so no
--           order-level attribution rule is needed. These breakdowns DO partition the
--           total and DO sum to it, unlike the per-method success rates of §1.9.
-- excludes: test transactions (§1.1); duplicate captures
with fx as (
    select c.rate_date,
           c.currency,
           cast(c.usd_per_unit / r.usd_per_unit as decimal(38,12)) as to_reporting
    from fx_rates c
    join fx_rates r on r.rate_date = c.rate_date and r.currency = 'INR'
),
captures as (
    select a.order_id, a.amount_minor, a.currency, a.business_date, a.method,
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
      and s.country_code = 'IN'
      and a.business_date between date '2026-07-01' and date '2026-07-31'
)
select c.method as key,
       cast(round(sum(c.amount_minor * fx.to_reporting)) as bigint) as value
from captures c join fx on fx.currency = c.currency and fx.rate_date = c.business_date
where c.capture_rank = 1 group by c.method order by value desc, key asc limit 5
