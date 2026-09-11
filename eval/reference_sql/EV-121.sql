-- qid:      EV-121
-- value:    days
-- shape:    series
-- window:   last_8_weeks       -> 2026-07-13 .. 2026-09-06   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   settlement lag (§2.13), weekly
-- scope:    country AE
-- currency: none
-- capability: finance (§2.13)
-- rule:     keyed on SETTLEMENT date (§2.13, §4.7), so each week is the week the money
--           SETTLED, not the week it was captured.
--           Eight COMPLETE Monday-Sunday weeks; the current partial week is excluded
--           (§1.6a). A series is matched by time key (ADR-009).
--           Unsettled captures have no lag and are excluded (§2.13).
-- excludes: test transactions (§1.1); unsettled captures
select cast(cast(date_trunc('week', st.settled_on) as date) as varchar) as key,
       cast(sum(st.settled_on - a.business_date) * 1.0 / count(*) as decimal(38,12)) as value
from settlements st
join settlement_items si on si.settlement_id = st.settlement_id
join payment_attempts a on a.attempt_id = si.attempt_id
join orders o on o.order_id = a.order_id
join showrooms s on s.showroom_id = o.showroom_id
where not a.is_test and a.status = 'captured' and s.country_code = 'AE'
  and st.settled_on between date '2026-07-13' and date '2026-09-06'
group by key order by key asc
