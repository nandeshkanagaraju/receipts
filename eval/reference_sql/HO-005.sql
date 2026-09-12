-- qid:      HO-005
-- value:    days
-- shape:    ranking
-- window:   july_2026          -> 2026-07-01 .. 2026-07-31   (on SETTLEMENT date, §2.13)
-- metric:   settlement lag (§2.13) by acquiring bank, for one payment method
-- scope:    country AE, method wallet
-- currency: none (a count of days, §2.13)
-- top_k:    10
-- rule:     the window keys on SETTLEMENT DATE, not capture date (§2.13, §4.7).
--           "What was our settlement lag in July" means payments SETTLED in July. A
--           settlement question answered on capture dates is wrong even though every
--           number in it is real.
--           The lag is settled_on minus the capture's own business date, in whole
--           days, averaged over the settled captures. Captures that have NOT settled
--           are excluded from the average -- they have no lag to measure -- and are
--           reported separately as unsettled amount (§2.14).
--           Only CAPTURED attempts are counted (§2.13). Since ADR-014 the settlement
--           tables also reference attempts that now read `authorized`, and those are
--           not captured payments.
--           The method lives on the attempt itself, so no attribution rule is needed
--           (§1.9, last paragraph).
--           The bank is the acquiring bank that settled the money; it is the same
--           bank the attempt carries, so the breakdown is unambiguous.
--           The average is cast to DECIMAL before dividing -- never float (D1).
-- excludes: test orders and test attempts (§1.1); unsettled captures
select st.acquiring_bank as key,
       cast(sum(cast(st.settled_on - a.business_date as bigint)) * 1.0 / count(*)
            as decimal(38,12)) as value
from settlement_items si
join settlements st on st.settlement_id = si.settlement_id
join payment_attempts a on a.attempt_id = si.attempt_id
join orders o on o.order_id = a.order_id
join showrooms s on s.showroom_id = o.showroom_id
where not a.is_test
  and not o.is_test
  and a.status = 'captured'
  and a.method = 'wallet'
  and s.country_code = 'AE'
  and st.settled_on between date '2026-07-01' and date '2026-07-31'
group by st.acquiring_bank
order by value desc, key asc
limit 10
