-- qid:      HO-B22
-- value:    money_minor
-- shape:    scalar
-- window:   pending_as_at_as_of -> snapshot as at 2026-09-09   (§2.14, §1.8)
-- metric:   unsettled amount (§2.14)
-- scope:    all countries
-- currency: USD (§1.4 rule 2 -- global_finance reports in US dollars)
-- rule:     "How much are we owed / waiting on / yet to receive" is UNSETTLED AMOUNT
--           (§5.1, §2.14) -- cash Kestrel has earned but not received. It is not
--           captured GMV and not settled money.
--           THIS IS A SNAPSHOT, NOT A FLOW (§2.14). "Right now" means as at the
--           reporting date: payments captured ON OR BEFORE it that had not settled by
--           it. §1.8 trims a window that runs past the last loaded business date, so the
--           snapshot date is 2026-09-09; the reporting day itself carries no data.
--           There is NO LOWER BOUND: a payment captured four months ago and still
--           unsettled is included, because unsettled cash does not age out.
--           Each amount converts at the daily rate for ITS OWN CAPTURE business date
--           (§2.14) -- the rate on the day the money was taken, not today's rate. That is
--           the same convention as captured GMV (§2.3), so the two reconcile: unsettled
--           amount is a subset of past captured GMV, valued identically.
--           Requires the finance capability (§2.14); the asker is global_finance.
--           The figure is always non-zero and always includes the last few days of
--           captures, which simply have not had time to settle (§2.14's note).
-- excludes: test orders and test attempts (§1.1); duplicate captures (§4.10)
with captures as (
    select a.attempt_id, a.order_id, a.amount_minor, a.currency, a.business_date,
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
),
settled_by_d as (
    select distinct si.attempt_id
    from settlement_items si
    join settlements st on st.settlement_id = si.settlement_id
    where st.settled_on <= date '2026-09-09'
)
select cast(round(sum(c.amount_minor * fx.to_reporting)) as bigint) as value
from captures c
join orders o on o.order_id = c.order_id
join fx on fx.currency = c.currency and fx.rate_date = c.business_date
left join settled_by_d sd on sd.attempt_id = c.attempt_id
where c.capture_rank = 1
  and not o.is_test
  and c.business_date <= date '2026-09-09'
  and sd.attempt_id is null
order by value
