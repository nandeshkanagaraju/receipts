-- qid:      HO-B19
-- value:    money_minor
-- shape:    scalar
-- window:   yesterday          -> 2026-09-09 .. 2026-09-09   (GLOSSARY §1.7, as_of 2026-09-10)
-- metric:   captured GMV (§2.3)
-- scope:    all countries
-- currency: USD (§1.4 rule 2 -- global_finance reports in US dollars)
-- rule:     "Total sales" is captured GMV -- money, not units (§6.1) -- and captured,
--           not settled: "how much did we take" and "how much has landed in the bank"
--           are different dates and different numbers (§5.1, §4.7).
--           THE RESERVED CURRENCY IS DISCLOSED. The question names none, so §1.4 rule 2
--           applies and the answer is in US dollars, the default for global finance; an
--           answer that does not say which currency it used is wrong even when the
--           arithmetic is right (§1.4).
--           Amounts in six currencies are NEVER added as raw minor numbers: that
--           produces a figure that is not money in any currency, and it looks entirely
--           plausible (§4.4). Each amount converts at the daily rate for ITS OWN capture
--           business date (§1.3), not one rate for the day's total.
--           "Yesterday" resolves PER SHOWROOM in that showroom's own timezone (§1.7):
--           every showroom's 9 September is included, even though they are different
--           absolute moments.
--           Captured money only, never authorised (§4.2); duplicates counted once
--           (§4.10).
-- excludes: test orders and test attempts (§1.1); duplicate captures
with captures as (
    select a.order_id, a.attempt_id, a.amount_minor, a.currency, a.business_date,
           a.method, a.acquiring_bank,
           row_number() over (
               partition by a.order_id, a.amount_minor
               order by a.attempt_no, a.attempt_id
           ) as capture_rank
    from payment_attempts a
    where a.status = 'captured'
      and not a.is_test
),
fx as (
    select c.rate_date,
           c.currency,
           cast(c.usd_per_unit / r.usd_per_unit as decimal(38,12)) as to_reporting
    from fx_rates c
    join fx_rates r on r.rate_date = c.rate_date and r.currency = 'USD'
)
select cast(round(sum(c.amount_minor * fx.to_reporting)) as bigint) as value
from captures c
join orders o on o.order_id = c.order_id
join fx on fx.currency = c.currency and fx.rate_date = c.business_date
where c.capture_rank = 1
  and not o.is_test
  and c.business_date = date '2026-09-09'
order by value
