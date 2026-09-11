-- qid:      EV-012
-- value:    money_minor
-- shape:    scalar
-- window:   august_2026        -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   NOT a Kestrel metric -- duplicate capture VALUE, per the row's `interpretation`
-- scope:    country IN
-- currency: INR (§1.4 rule 1 -- "in rupees")
-- rule:     interpretation: "sum of amounts on non-test captured attempts that are
--           duplicates of another capture on the same order, at Indian showrooms, keyed
--           on capture business date, in INR."
--           §2.15 defines the COUNT and notes the value is available separately; the
--           value itself is not a Kestrel metric, which is why this row is annotated.
--           For a PAIR the duplicate is one row: one capture is legitimate, one is the
--           duplicate (§2.15). The duplicate side is what is summed here -- and it is the
--           same side that captured GMV drops so revenue is not overstated (§4.10).
--           A row containing 0 is returned if none (docs/M2_NOTES.md §5).
-- excludes: test transactions (§1.1)
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
      and s.country_code = 'IN'
      and a.business_date between date '2026-08-01' and date '2026-08-31'
)
select cast(round(coalesce(sum(c.amount_minor * fx.to_reporting), 0)) as bigint) as value
from captures c
join fx on fx.currency = c.currency and fx.rate_date = c.business_date
where c.capture_rank > 1
