-- qid:      EV-080
-- value:    seconds
-- shape:    scalar
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   NOT a Kestrel metric -- order-to-first-attempt time in SECONDS, per the row's `interpretation`
-- scope:    all countries
-- currency: none
-- rule:     interpretation: "mean difference in seconds between an order's
--           created_at_utc and the created_at_utc of its earliest non-test payment
--           attempt, across non-test orders in the last complete calendar month, reported
--           in seconds. Not a Kestrel metric; it reads stored timestamps and no clock."
--           THIS IS THE ONE PLACE A UTC TIMESTAMP IS THE RIGHT KEY. §1.2 keys metrics on
--           business date "unless the definition explicitly says otherwise", and an
--           elapsed duration is exactly that: the gap between two moments is the same
--           number in any timezone, so converting to local dates would destroy it. §4.5
--           forbids deriving a business DAY from a timestamp, which is a different thing.
--           The window itself still selects on the order's BUSINESS date.
--           as_of is injected; no clock is read (D2).
-- excludes: test orders and test attempts (§1.1)
with first_attempt as (
    select a.order_id, min(a.created_at_utc) as first_attempt_at
    from payment_attempts a
    where not a.is_test
    group by a.order_id
)
select cast(
           sum(date_diff('second', o.created_at_utc, f.first_attempt_at)) * 1.0 / count(*)
       as decimal(38,12)) as value
from orders o
join first_attempt f on f.order_id = o.order_id
where not o.is_test
  and o.business_date between date '2026-08-01' and date '2026-08-31'
order by value
