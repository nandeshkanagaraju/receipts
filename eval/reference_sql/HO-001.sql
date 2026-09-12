-- qid:      HO-001
-- value:    money_minor
-- shape:    compare
-- window:   this_month_to_date -> 2026-09-01 .. 2026-09-09 against 2026-08-01 .. 2026-08-09
--           (the comparison window is the SAME DAYS of the previous month, §1.6a)
-- metric:   captured GMV (§2.3), broken down by country
-- scope:    all countries
-- currency: USD (§1.4 rule 1 -- the asker named it)
-- top_k:    6
-- rule:     EQUAL-LENGTH WINDOWS (§1.6a, SDD §9.1 rule 5). Month-to-date ends
--           YESTERDAY -- nine days -- and the comparison is the SAME NINE DAYS of
--           the previous month, not the whole of the previous month. Comparing nine
--           days against thirty-one would show a collapse in every additive metric
--           every month as an artefact of the calendar.
--           Captured money only, never authorised (§4.2): since ADR-014 the world
--           carries authorised-and-never-captured rows, so `status = 'captured'` and
--           `status <> 'failed'` are materially different and only the first is
--           revenue.
--           Each amount converts at the daily rate for its OWN capture business date
--           (§1.3, §4.4), never one rate for the window. Raw minor units are never
--           added across currencies.
--           Both values are returned per country, keyed `<country>|current` and
--           `<country>|comparison` (ADR-009): a system that silently drops the
--           comparison has not answered a question about a change.
--           Every country appears in both windows; a country with no captures is an
--           exact zero rather than a missing row (docs/M2_NOTES.md §5).
-- excludes: test orders and test attempts (§1.1); the duplicate side of a duplicate
--           capture (§2.3, §4.10)
with fx as (
    select c.rate_date,
           c.currency,
           cast(c.usd_per_unit / r.usd_per_unit as decimal(38,12)) as to_reporting
    from fx_rates c
    join fx_rates r on r.rate_date = c.rate_date and r.currency = 'USD'
),
captures as (
    select a.order_id, a.amount_minor, a.currency, a.business_date,
           row_number() over (
               partition by a.order_id, a.amount_minor
               order by a.attempt_no, a.attempt_id
           ) as capture_rank
    from payment_attempts a
    where a.status = 'captured'
      and not a.is_test
),
windows as (
    select 'current' as label, date '2026-09-01' as lo, date '2026-09-09' as hi
    union all
    select 'comparison', date '2026-08-01', date '2026-08-09'
),
spine as (
    select co.country_code, w.label
    from countries co
    cross join windows w
),
valued as (
    select s.country_code,
           w.label,
           sum(c.amount_minor * fx.to_reporting) as amount
    from captures c
    join orders o on o.order_id = c.order_id
    join showrooms s on s.showroom_id = o.showroom_id
    join windows w on c.business_date between w.lo and w.hi
    join fx on fx.currency = c.currency and fx.rate_date = c.business_date
    where c.capture_rank = 1
      and not o.is_test
    group by s.country_code, w.label
)
select sp.country_code || '|' || sp.label as key,
       cast(round(coalesce(v.amount, 0)) as bigint) as value
from spine sp
left join valued v on v.country_code = sp.country_code and v.label = sp.label
order by key asc
