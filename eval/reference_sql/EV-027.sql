-- qid:      EV-027
-- value:    money_minor
-- shape:    ranking
-- window:   july_2026          -> 2026-07-01 .. 2026-07-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   net revenue (§2.5), by country
-- scope:    all countries
-- currency: USD (§1.4 rule 1 -- the asker named it)
-- top_k:    6
-- rule:     captured GMV minus refunds PROCESSED in the same window (§2.5). A refund
--           processed in July against a June capture reduces July, not June -- holding a
--           month open until every possible refund landed would mean no month ever closes.
--           Every amount converts at the daily rate for its own date before subtracting
--           in the reporting currency (§2.5, §4.4); raw minor units are never summed
--           across currencies.
--           Net revenue can be negative for a narrow slice; that is a real result (§2.5).
-- excludes: test transactions (§1.1); pending and failed refunds; duplicate captures
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
      and a.business_date between date '2026-07-01' and date '2026-07-31'
),
captured as (
    select c.country_code, sum(c.amount_minor * fx.to_reporting) as amount
    from captures c join fx on fx.currency = c.currency and fx.rate_date = c.business_date
    where c.capture_rank = 1 group by c.country_code
),
refunded as (
    select s.country_code, sum(rf.amount_minor * fx.to_reporting) as amount
    from refunds rf
    join orders o on o.order_id = rf.order_id
    join showrooms s on s.showroom_id = o.showroom_id
    join fx on fx.currency = rf.currency and fx.rate_date = rf.business_date
    where not o.is_test and rf.status = 'processed'
      and rf.business_date between date '2026-07-01' and date '2026-07-31'
    group by s.country_code
)
select captured.country_code as key,
       cast(round(captured.amount - coalesce(refunded.amount, 0)) as bigint) as value
from captured left join refunded on refunded.country_code = captured.country_code
order by value desc, key asc limit 6
