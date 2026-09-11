-- qid:      EV-113
-- value:    days
-- shape:    scalar
-- window:   july_2026          -> 2026-07-01 .. 2026-07-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   settlement lag (§2.13) for wallet payments
-- scope:    country SG, wallet attempts only
-- currency: none
-- capability: finance (§2.13)
-- rule:     keyed on SETTLEMENT date, not capture date (§2.13, §4.7): "lag in July"
--           means payments SETTLED in July.
--           "Wallet payments" is a method filter on the ATTEMPTS that settled, not an
--           order-level attribution: settlement attaches to a capture, and every capture
--           already carries its own method (§1.9).
--           Unsettled captures have no lag and are excluded from the average; they are
--           reported separately as unsettled amount (§2.14), so the two must be read
--           together or the average understates a delay.
-- excludes: test transactions (§1.1); unsettled captures
select cast(sum(st.settled_on - a.business_date) * 1.0 / count(*) as decimal(38,12)) as value
from settlements st
join settlement_items si on si.settlement_id = st.settlement_id
join payment_attempts a on a.attempt_id = si.attempt_id
join orders o on o.order_id = a.order_id
join showrooms s on s.showroom_id = o.showroom_id
where not a.is_test and a.status = 'captured' and a.method = 'wallet'
  and s.country_code = 'SG'
  and st.settled_on between date '2026-07-01' and date '2026-07-31'
order by value
