-- qid:      DV-032
-- value:    money_minor
-- shape:    scalar
-- window:   august_2026        -> 2026-08-01 .. 2026-08-31   (named month, as_of 2026-09-10)
-- metric:   NOT a Kestrel metric -- authorised-not-captured value, per the row's `interpretation`
-- scope:    all countries
-- currency: USD (§1.4 rule 1 -- the asker named it)
-- rule:     interpretation: "sum of amounts on non-test payment attempts that
--           reached authorised status where no attempt on the same order was
--           captured. Keyed on attempt business date, converted to USD at each
--           attempt's own daily rate."
--           §4.2: an authorisation reserves funds, a capture takes them, and
--           only the capture is revenue. This question asks for the gap itself.
--           FLAG -- THIS REFERENCE IS ZERO, AND ZERO IS THE HONEST ANSWER FOR
--           THIS WORLD, BUT NOT FOR THE REASON THE QUESTION EXPECTS.
--           SDD §5.2 declares payment_attempts.status in
--           ('authorized', 'captured', 'failed'). The generated artifact holds
--           only 'captured' and 'failed': not one attempt reached authorised
--           status, so the authorised-not-captured set is empty by construction
--           rather than because Kestrel captures everything it authorises.
--           kestrel_gen is frozen at gen-frozen, so this is recorded in
--           LIMITATIONS.md and not fixed. The predicate is written against the
--           SDD's spelling so it stays correct if the world is ever regenerated.
--           A row containing 0 is returned, never zero rows: an empty result and
--           a result of zero are different claims (docs/M2_NOTES.md §5).
-- excludes: test attempts (§1.1)
with fx as (
    select c.rate_date,
           c.currency,
           cast(c.usd_per_unit / r.usd_per_unit as decimal(38,12)) as to_reporting
    from fx_rates c
    join fx_rates r on r.rate_date = c.rate_date and r.currency = 'USD'
),
captured_orders as (
    select distinct a.order_id
    from payment_attempts a
    where a.status = 'captured'
      and not a.is_test
)
select cast(round(coalesce(sum(a.amount_minor * fx.to_reporting), 0)) as bigint) as value
from payment_attempts a
join fx on fx.currency = a.currency and fx.rate_date = a.business_date
where not a.is_test
  and a.status = 'authorized'
  and a.business_date between date '2026-08-01' and date '2026-08-31'
  and a.order_id not in (select order_id from captured_orders)
order by value
