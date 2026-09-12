-- qid:      HO-033
-- value:    count
-- shape:    scalar
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   method-switch order count -- NOT a glossary metric; the row's
--           `interpretation` governs (ADR-009)
-- scope:    country GB
-- currency: none (a count)
-- rule:     the row carries an `interpretation` because the glossary defines the two
--           attribution rules -- "tried" for success rates (§1.9) and "paying" for
--           everything else (§5.3a) -- but no count of the orders that move between
--           them, and that sentence governs.
--           An order counts when the method of its CAPTURED attempt differs from the
--           method of its FIRST non-test attempt. This is §4.1 and §1.9 made
--           countable: these are exactly the retry-switchers whose existence is why a
--           per-method success rate must not use final-attempt attribution, because
--           each of them would otherwise vanish from the denominator of the method
--           that failed them.
--           "First attempt" is the lowest attempt_no among non-test attempts; where an
--           order has more than one capture the earliest capturing attempt decides, so
--           the answer is deterministic.
--           Keyed on ORDER business date (the interpretation's date key).
--           Only orders that reached paid status can switch -- an order never captured
--           has no paying method at all (§5.3a).
-- excludes: test orders and test attempts (§1.1)
with scoped as (
    select o.order_id
    from orders o
    join showrooms s on s.showroom_id = o.showroom_id
    where not o.is_test
      and s.country_code = 'GB'
      and o.business_date between date '2026-08-01' and date '2026-08-31'
),
attempts as (
    select a.order_id, a.attempt_no, a.attempt_id, a.method, a.status
    from payment_attempts a
    join scoped sc on sc.order_id = a.order_id
    where not a.is_test
),
first_method as (
    select order_id,
           first(method order by attempt_no asc, attempt_id asc) as method
    from attempts
    group by order_id
),
paying_method as (
    select order_id,
           first(method order by attempt_no asc, attempt_id asc) as method
    from attempts
    where status = 'captured'
    group by order_id
)
select count(*) as value
from paying_method p
join first_method f on f.order_id = p.order_id
where p.method <> f.method
order by value
