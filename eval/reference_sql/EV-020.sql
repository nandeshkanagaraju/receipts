-- qid:      EV-020
-- value:    ratio
-- shape:    scalar
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   NOT a Kestrel metric -- pay-later share of PAID orders, per the row's `interpretation`
-- scope:    country GB
-- currency: none
-- rule:     interpretation: "distinct non-test PAID orders at UK showrooms whose
--           captured attempt used method 'pay_later', divided by all distinct non-test
--           paid orders at UK showrooms in the window, keyed on order business date."
--           "Orders paid with pay-later" is a method-qualified order set, so it uses the
--           PAYING method (§5.3a), not the tried rule of §1.9. An order that tried
--           pay-later and paid by card is a card order.
--           A method share of paid orders is not a Kestrel metric; EMI share (§2.11) is a
--           share of VALUE, not of orders, and answering that here answers a different
--           question.
-- excludes: test orders and test attempts (§1.1)
with paid_orders as (
    select o.order_id,
           max(case when a.method = 'pay_later' then 1 else 0 end) as paid_by_pay_later
    from orders o
    join showrooms s on s.showroom_id = o.showroom_id
    join payment_attempts a on a.order_id = o.order_id
    where not o.is_test and not a.is_test and a.status = 'captured'
      and s.country_code = 'GB'
      and o.business_date between date '2026-08-01' and date '2026-08-31'
    group by o.order_id
)
select cast(sum(paid_by_pay_later) * 1.0 / count(*) as decimal(38,12)) as value
from paid_orders
order by value
