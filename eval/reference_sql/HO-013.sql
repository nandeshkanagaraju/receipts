-- qid:      HO-013
-- value:    money_minor
-- shape:    scalar
-- window:   calendar_q2_2026   -> 2026-04-01 .. 2026-06-30
-- metric:   net revenue (§2.5)
-- scope:    all countries
-- currency: USD (§1.4 rule 1 -- the asker named it)
-- rule:     the question names the CALENDAR quarter explicitly, so it is not
--           ambiguous and is answered directly (§4.6, §6.2). Kestrel's fiscal year
--           starts on 1 April, so fiscal Q2 of FY2026 would be July-September 2025 --
--           a different window and a different number. An unqualified "Q2" would have
--           to be clarified; "calendar Q2 2026" must not be.
--           Net revenue is captured GMV minus refunds PROCESSED in the same window
--           (§2.5), each side keyed on its own date -- captures on capture business
--           date, refunds on refund business date.
--           Each amount converts at the daily rate for its OWN business date (§1.3,
--           §4.4), per side, and the two are subtracted in the reporting currency
--           (§2.5). Raw minor units are never added across the six currencies: that
--           would be money in no currency, and it looks entirely plausible.
-- excludes: test orders and test attempts (§1.1); pending and failed refunds (§2.4);
--           duplicate captures (§4.10)
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
captured as (
    select sum(c.amount_minor * fx.to_reporting) as amount
    from captures c
    join orders o on o.order_id = c.order_id
    join fx on fx.currency = c.currency and fx.rate_date = c.business_date
    where c.capture_rank = 1
      and not o.is_test
      and c.business_date between date '2026-04-01' and date '2026-06-30'
),
refunded as (
    select sum(rf.amount_minor * fx.to_reporting) as amount
    from refunds rf
    join orders o on o.order_id = rf.order_id
    join fx on fx.currency = rf.currency and fx.rate_date = rf.business_date
    where not o.is_test
      and rf.status = 'processed'
      and rf.business_date between date '2026-04-01' and date '2026-06-30'
)
select cast(round(coalesce((select amount from captured), 0)
                  - coalesce((select amount from refunded), 0)) as bigint) as value
order by value
