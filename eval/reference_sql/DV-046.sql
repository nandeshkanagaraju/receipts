-- qid:      DV-046
-- value:    days
-- shape:    ranking
-- window:   august_2026        -> 2026-08-01 .. 2026-08-31   (named month, as_of 2026-09-10)
-- metric:   settlement lag (§2.13), by acquiring bank, for EMI orders
-- scope:    all countries, EMI-paid orders only
-- currency: none
-- top_k:    10
-- capability: finance (§2.13)
-- rule:     keyed on SETTLEMENT date, not capture date (§2.13, §4.7). Captures
--           not yet settled have no lag and are excluded (§2.13).
--           "EMI orders" means orders whose CAPTURED attempt used EMI (§5.3a) --
--           the method the money actually came in on, not a method that was
--           merely tried. The tried rule of §1.9 applies to success rates only.
--           ACQUIRING bank, not issuing: the acquiring bank is Kestrel's, and
--           the two are different dimensions (§1.9).
-- excludes: test transactions (§1.1); unsettled captures
select st.acquiring_bank as key,
       cast(sum(st.settled_on - a.business_date) * 1.0 / count(*) as decimal(38,12)) as value
from settlements st
join settlement_items si on si.settlement_id = st.settlement_id
join payment_attempts a on a.attempt_id = si.attempt_id
where not a.is_test
  and a.status = 'captured'
  and a.method = 'emi'
  and st.settled_on between date '2026-08-01' and date '2026-08-31'
group by st.acquiring_bank
order by value desc, key asc
limit 10
