-- qid:      EV-024
-- value:    count
-- shape:    scalar
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   NOT a Kestrel metric -- multi-attempt order count, per the row's `interpretation`
-- scope:    country GB
-- currency: none
-- rule:     interpretation: "distinct non-test orders at UK showrooms in the window
--           having two or more non-test payment attempts, keyed on order business date."
--           This is the attempts-versus-orders distinction made explicit (§4.1): a
--           customer who fails once and succeeds on the retry is TWO attempts and ONE
--           order, and this counts the orders where that happened.
--           Retry counts are not a Kestrel metric.
-- excludes: test orders and test attempts (§1.1)
with per_order as (
    select o.order_id, count(*) as attempts
    from orders o
    join showrooms s on s.showroom_id = o.showroom_id
    join payment_attempts a on a.order_id = o.order_id and not a.is_test
    where not o.is_test and s.country_code = 'GB'
      and o.business_date between date '2026-08-01' and date '2026-08-31'
    group by o.order_id
)
select count(*) as value from per_order where attempts >= 2
order by value
