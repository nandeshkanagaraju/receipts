-- qid:      EV-017
-- value:    days
-- shape:    ranking
-- window:   july_2026          -> 2026-07-01 .. 2026-07-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   settlement lag (§2.13) for EMI orders, by acquiring bank
-- scope:    country MY, EMI-paid orders only
-- currency: none
-- top_k:    10
-- capability: finance (§2.13)
-- rule:     keyed on SETTLEMENT date, not capture date (§2.13, §4.7).
--           "EMI orders" means orders whose CAPTURED attempt used EMI (§5.3a) -- the
--           method the money actually came in on. This is deliberately NOT the "tried"
--           rule of §1.9, which applies to success rates only.
--           ACQUIRING bank is Kestrel's bank; issuing bank is the customer's. They are
--           different dimensions and a synonym list that merges them is wrong (§1.9).
--           EMI is offered only in India and Malaysia (§2.11), so Malaysia is one of the
--           two countries where this is non-empty.
-- excludes: test transactions (§1.1); unsettled captures
select st.acquiring_bank as key,
       cast(sum(st.settled_on - a.business_date) * 1.0 / count(*) as decimal(38,12)) as value
from settlements st
join settlement_items si on si.settlement_id = st.settlement_id
join payment_attempts a on a.attempt_id = si.attempt_id
join orders o on o.order_id = a.order_id
join showrooms s on s.showroom_id = o.showroom_id
where not a.is_test and a.status = 'captured' and a.method = 'emi'
  and s.country_code = 'MY'
  and st.settled_on between date '2026-07-01' and date '2026-07-31'
group by st.acquiring_bank order by value desc, key asc limit 10
