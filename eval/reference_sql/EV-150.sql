-- qid:      EV-150
-- value:    days
-- shape:    list
-- window:   pending_as_at_as_of -> 2025-03-01 .. 2026-09-09   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   refund age (§2.4a) over pending gateway refunds (§6.3)
-- scope:    all countries
-- currency: none
-- source:   gateway
-- rule:     refund age is the REPORTING DATE minus the refund's CREATION business date,
--           in whole days (§2.4a) -- not the processed date; an unprocessed refund has no
--           processed date.
--           "The oldest" is a single record, but ties are possible and every tied record
--           is equally the answer, so the shape is a LIST compared as a SET
--           (docs/M2_NOTES.md §5) rather than a scalar that would have to pick one.
--           No window: "still pending" is a snapshot as at the reporting date and nothing
--           ages out (§2.14's posture, §6.3).
--           as_of is injected; no clock is read (D2).
--           Membership comes from truth/constructed.json (D11).
-- excludes: test transactions via the joined order (refunds carry no flag)
with pending as (
    select rf.refund_id,
           cast(date '2026-09-10' - rf.business_date as bigint) as age_days
    from refunds rf
    join orders o on o.order_id = rf.order_id
    where not o.is_test and rf.status = 'pending'
)
select refund_id as key, age_days as value
from pending
where age_days = (select max(age_days) from pending)
order by key asc
