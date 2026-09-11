-- qid:      HO-053
-- value:    money_minor
-- shape:    list
-- window:   pending_as_at_as_of -> 2025-03-01 .. 2026-09-09   (a snapshot, as_of 2026-09-10)
-- metric:   refunds still pending at the gateway (§6.3), above a value threshold
-- scope:    country GB
-- currency: GBP (§1.4 rule 1 -- the asker named it, "£500")
-- source:   gateway
-- rule:     §6.3 -- in a LIVE gateway question "refunds" means the individual refund
--           RECORDS, not the §2.4 refunded-amount metric, which counts refunds
--           PROCESSED in a window and explicitly excludes pending ones. Answering with
--           a single total would be wrong.
--           The shape is a LIST, compared as a SET: membership decides correctness and
--           order does not (docs/M2_NOTES.md §5). A list is also the one shape for which
--           an empty result is a legitimate answer -- "none are over £500" is a true
--           claim and there is no row containing 0 that would say it.
--           "Still pending" is a SNAPSHOT as at the reporting date with no lower bound,
--           the same posture as unsettled amount (§2.14). No record ages out.
--           "More than £500" is STRICTLY greater than 50,000 pence -- money is stored in
--           the minor unit of its own currency (§1.3). The scope is one country and one
--           currency, so the threshold applies to the stored amount directly and no
--           conversion arises.
--           Membership is decided by truth/constructed.json, written at construction
--           (D11); this query computes the warehouse's mirror of it and
--           evalkit.reference requires the two to agree.
-- excludes: test transactions, via the joined order (refunds carry no flag of their own)
select rf.refund_id as key,
       cast(rf.amount_minor as bigint) as value
from refunds rf
join orders o on o.order_id = rf.order_id
join showrooms s on s.showroom_id = o.showroom_id
where not o.is_test
  and rf.status = 'pending'
  and s.country_code = 'GB'
  and rf.amount_minor > 50000
order by key asc
