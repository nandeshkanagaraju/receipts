-- qid:      EV-069
-- value:    days
-- shape:    ranking
-- window:   july_2026          -> 2026-07-01 .. 2026-07-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   settlement lag (§2.13) for card payments, by card network
-- scope:    country GB, card attempts only
-- currency: none
-- top_k:    5
-- capability: finance (§2.13)
-- rule:     keyed on SETTLEMENT date (§2.13, §4.7).
--           Card NETWORK is the scheme the card runs on, a different dimension from the
--           issuing and acquiring banks (§1.9); it is null for non-card methods, which is
--           why the filter is on method rather than on the network being present.
--           Unsettled captures have no lag and are excluded (§2.13).
-- excludes: test transactions (§1.1); unsettled captures
select a.card_network as key,
       cast(sum(st.settled_on - a.business_date) * 1.0 / count(*) as decimal(38,12)) as value
from settlements st
join settlement_items si on si.settlement_id = st.settlement_id
join payment_attempts a on a.attempt_id = si.attempt_id
join orders o on o.order_id = a.order_id
join showrooms s on s.showroom_id = o.showroom_id
where not a.is_test and a.status = 'captured' and a.method = 'card'
  and a.card_network is not null and s.country_code = 'GB'
  and st.settled_on between date '2026-07-01' and date '2026-07-31'
group by a.card_network order by value desc, key asc limit 5
