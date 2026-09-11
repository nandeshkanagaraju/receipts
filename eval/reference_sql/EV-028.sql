-- qid:      EV-028
-- value:    ratio
-- shape:    ranking
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   refund rate (§2.7), by showroom
-- scope:    country GB
-- currency: GBP (§1.4 rule 2 -- store_ops_uk reports in GBP); both sides converted before dividing
-- top_k:    5
-- rule:     refund rate is VALUE-based (§2.7). "Highest refund rate" names the metric,
--           so this is not the undefined word "worst" (§5.5): the question says which
--           quantity to rank on.
--           Each side keeps its own date key (§2.7). A showroom with captures but no
--           refunds has a rate of exactly 0 and stays in the ranking -- an exact-zero cell,
--           not a missing one (docs/M2_NOTES.md §5).
-- excludes: test transactions (§1.1); pending and failed refunds; duplicate captures
with fx as (
    select c.rate_date,
           c.currency,
           cast(c.usd_per_unit / r.usd_per_unit as decimal(38,12)) as to_reporting
    from fx_rates c
    join fx_rates r on r.rate_date = c.rate_date and r.currency = 'GBP'
),
captures as (
    select a.order_id, a.amount_minor, a.currency, a.business_date, o.showroom_id,
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
      and a.business_date between date '2026-08-01' and date '2026-08-31'
),
captured as (
    select c.showroom_id, sum(c.amount_minor * fx.to_reporting) as amount
    from captures c join fx on fx.currency = c.currency and fx.rate_date = c.business_date
    where c.capture_rank = 1 group by c.showroom_id
),
refunded as (
    select o.showroom_id, sum(rf.amount_minor * fx.to_reporting) as amount
    from refunds rf
    join orders o on o.order_id = rf.order_id
    join showrooms s on s.showroom_id = o.showroom_id
    join fx on fx.currency = rf.currency and fx.rate_date = rf.business_date
    where not o.is_test and rf.status = 'processed' and s.country_code = 'GB'
      and rf.business_date between date '2026-08-01' and date '2026-08-31'
    group by o.showroom_id
)
select sh.name as key,
       cast(coalesce(refunded.amount, 0) / captured.amount as decimal(38,12)) as value
from captured
left join refunded on refunded.showroom_id = captured.showroom_id
join showrooms sh on sh.showroom_id = captured.showroom_id
order by value desc, key asc limit 5
