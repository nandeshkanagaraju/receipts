-- qid:      EV-008
-- value:    days
-- shape:    ranking
-- window:   july_2026          -> 2026-07-01 .. 2026-07-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   settlement lag (§2.13), by acquiring bank
-- scope:    all countries
-- currency: none
-- top_k:    10
-- capability: finance (§2.13)
-- rule:     the window keys on SETTLEMENT date, not capture date (§2.13, §4.7): "lag in
--           July" means payments SETTLED in July. A settlement question answered on
--           capture dates is wrong even though every number in it is real.
--           Captures not yet settled have no lag to measure and are excluded from the
--           average; they are reported separately as unsettled amount (§2.14), so the
--           average understates the problem when settlement is delayed and the two must
--           be read together.
-- excludes: test transactions (§1.1); unsettled captures
select st.acquiring_bank as key,
       cast(sum(st.settled_on - a.business_date) * 1.0 / count(*) as decimal(38,12)) as value
from settlements st
join settlement_items si on si.settlement_id = st.settlement_id
join payment_attempts a on a.attempt_id = si.attempt_id
where not a.is_test
  and a.status = 'captured'
  and st.settled_on between date '2026-07-01' and date '2026-07-31'
group by st.acquiring_bank
order by value desc, key asc
limit 10
