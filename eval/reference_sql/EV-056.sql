-- qid:      EV-056
-- value:    days
-- shape:    ranking
-- window:   august_2026        -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   settlement lag (§2.13), by country
-- scope:    all countries
-- currency: none
-- top_k:    6
-- capability: finance (§2.13)
-- rule:     keyed on SETTLEMENT date, not capture date (§2.13, §4.7): a settlement
--           question answered on capture dates is wrong even though every number in it is
--           real. Unsettled captures have no lag and are excluded (§2.13).
-- excludes: test transactions (§1.1); unsettled captures
select s.country_code as key,
       cast(sum(st.settled_on - a.business_date) * 1.0 / count(*) as decimal(38,12)) as value
from settlements st
join settlement_items si on si.settlement_id = st.settlement_id
join payment_attempts a on a.attempt_id = si.attempt_id
join orders o on o.order_id = a.order_id
join showrooms s on s.showroom_id = o.showroom_id
where not a.is_test and a.status = 'captured'
  and st.settled_on between date '2026-08-01' and date '2026-08-31'
group by s.country_code order by value desc, key asc limit 6
