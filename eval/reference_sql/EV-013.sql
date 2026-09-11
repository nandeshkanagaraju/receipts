-- qid:      EV-013
-- value:    money_minor
-- shape:    compare
-- window:   this_month_to_date -> 2026-09-01 .. 2026-09-09   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   net revenue (§2.5)
-- scope:    all countries
-- currency: USD (§1.4 rule 1 -- the asker named it)
-- rule:     EQUAL-LENGTH WINDOWS (§1.6a, SDD §9.1 rule 5). "This month" is
--           month-to-date -- 1-9 September, NINE days -- and the comparison is the SAME
--           DAYS of the previous month, 1-9 August, also nine days. It is NOT the whole of
--           August: comparing nine days against thirty-one would show a collapse in every
--           additive metric every month, purely as a calendar artefact.
--           Both values are returned, keyed `current` and `comparison` (ADR-009): a system
--           that silently drops the comparison has not answered a question about a change.
--           Net revenue is captured GMV in the window MINUS refunds PROCESSED in the same
--           window (§2.5) -- not the refunds that eventually attach to the window's
--           captures. Each side converts at its own date, then subtracts in USD.
-- excludes: test transactions (§1.1); pending and failed refunds; duplicate captures
with fx as (
    select c.rate_date,
           c.currency,
           cast(c.usd_per_unit / r.usd_per_unit as decimal(38,12)) as to_reporting
    from fx_rates c
    join fx_rates r on r.rate_date = c.rate_date and r.currency = 'USD'
),
periods as (
    select date '2026-09-01' as lo, date '2026-09-09' as hi, 'current' as period
    union all
    select date '2026-08-01', date '2026-08-09', 'comparison'
),
captures as (
    select a.order_id, a.amount_minor, a.currency, a.business_date, p.period,
           row_number() over (
               partition by a.order_id, a.amount_minor
               order by a.attempt_no, a.attempt_id
           ) as capture_rank
    from payment_attempts a
    join periods p on a.business_date between p.lo and p.hi
    where a.status = 'captured' and not a.is_test
),
captured as (
    select c.period, sum(c.amount_minor * fx.to_reporting) as amount
    from captures c
    join fx on fx.currency = c.currency and fx.rate_date = c.business_date
    where c.capture_rank = 1
    group by c.period
),
refunded as (
    select p.period, sum(rf.amount_minor * fx.to_reporting) as amount
    from refunds rf
    join orders o on o.order_id = rf.order_id
    join periods p on rf.business_date between p.lo and p.hi
    join fx on fx.currency = rf.currency and fx.rate_date = rf.business_date
    where not o.is_test and rf.status = 'processed'
    group by p.period
)
select captured.period as key,
       cast(round(captured.amount - coalesce(refunded.amount, 0)) as bigint) as value
from captured left join refunded on refunded.period = captured.period
order by key asc
