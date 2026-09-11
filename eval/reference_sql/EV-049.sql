-- qid:      EV-049
-- value:    count
-- shape:    ranking
-- window:   pending_as_at_as_of -> 2025-03-01 .. 2026-09-09   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   refunds still pending at the gateway (§6.3), counted by country
-- scope:    all countries
-- currency: none
-- top_k:    6
-- rule:     §6.3 -- in a gateway question "refunds" means the RECORDS the gateway is
--           holding, not a refunded total. This question asks how MANY, by country, so the
--           answer is a count and not the §2.4 refunded amount.
--           There is no date window in the question: "still pending" is a snapshot as at
--           the reporting date, so every pending record counts however old it is -- the
--           same posture as unsettled amount (§2.14), which also does not age out.
--           A country with no pending refunds is an exact zero, not a missing row; none
--           of the six is empty here.
-- excludes: test transactions via the joined order (refunds carry no flag)
select s.country_code as key, count(*) as value
from refunds rf
join orders o on o.order_id = rf.order_id
join showrooms s on s.showroom_id = o.showroom_id
where not o.is_test and rf.status = 'pending'
group by s.country_code order by value desc, key asc limit 6
