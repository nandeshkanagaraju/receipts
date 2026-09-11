-- qid:      HO-B06
-- value:    count
-- shape:    scalar
-- window:   yesterday          -> 2026-09-09 .. 2026-09-09   (GLOSSARY §1.7, as_of 2026-09-10)
-- metric:   a count of refund records processed -- NOT a glossary metric; the row's
--           `interpretation` governs (ADR-009)
-- scope:    region IN-TN (Tamil Nadu)
-- currency: none (a count)
-- rule:     the row carries an `interpretation` because §2.4 defines the refunded
--           AMOUNT and §6.1 defaults "refunds" as a noun to that amount. A plain COUNT
--           of refund records is answerable from the tables but is not a Kestrel
--           metric, and the question asks how MANY.
--           "Processed" is the refund's own status, and the window keys on the REFUND
--           business date -- the local date the refund was processed, not the date of
--           the order being refunded (§2.4, §1.2). Pending and failed refunds are not
--           counted (§2.4).
--           This is a count of refunds, not of refunded orders: an order refunded twice
--           contributes two records, which is the reading "how many refunds" asks for
--           and is also why partial refunds matter here (§4.3).
--           "Yesterday" is the showroom's own local business date (§1.7, §4.5).
-- excludes: test transactions, via the joined order (refunds carry no flag of their own)
select count(*) as value
from refunds rf
join orders o on o.order_id = rf.order_id
join showrooms s on s.showroom_id = o.showroom_id
where not o.is_test
  and rf.status = 'processed'
  and s.region_id = 'IN-TN'
  and rf.business_date = date '2026-09-09'
order by value
