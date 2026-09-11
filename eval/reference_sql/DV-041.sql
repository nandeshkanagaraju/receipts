-- qid:      DV-041
-- value:    money_minor
-- shape:    compare
-- window:   this_month_to_date -> 2026-09-01 .. 2026-09-09 against 2026-08-01 .. 2026-08-09
--           (the comparison window is the SAME DAYS of the previous month, §1.6a)
-- metric:   captured GMV (§2.3)
-- scope:    region IN-TN (Tamil Nadu)
-- currency: INR (§1.4 rule 2 -- rm_tamil_nadu reports in INR)
-- rule:     EQUAL-LENGTH WINDOWS (§1.6a, SDD §9.1 rule 5). "This month" is
--           month-to-date -- 1-9 September, NINE days -- and the comparison is
--           the SAME DAYS of the previous month, 1-9 August, also nine days. It
--           is NOT the whole of August. Comparing nine days against thirty-one
--           would show a collapse in every additive metric every month, purely
--           as an artefact of the calendar.
--           Both values are returned, keyed `current` and `comparison`
--           (ADR-009): a system that silently drops the comparison has not
--           answered a question about a change.
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
    where a.status = 'captured'
      and not a.is_test
      and not o.is_test
      and s.region_id = 'IN-TN'
      and (a.business_date between date '2026-09-01' and date '2026-09-09'
        or a.business_date between date '2026-08-01' and date '2026-08-09')
)
select case when c.business_date >= date '2026-09-01' then 'current' else 'comparison' end as key,
       cast(round(sum(c.amount_minor * fx.to_reporting)) as bigint) as value
from captures c
join fx on fx.currency = c.currency and fx.rate_date = c.business_date
where c.capture_rank = 1
group by key
order by key asc
