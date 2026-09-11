-- qid:      HO-054
-- value:    count
-- shape:    list
-- window:   pending_as_at_as_of -> 2025-03-01 .. 2026-09-09   (a snapshot, as_of 2026-09-10)
-- metric:   refunds still pending at the gateway (§6.3), by showroom
-- scope:    region IN-TN (Tamil Nadu)
-- currency: none (a count)
-- rule:     §6.3 -- a gateway question asks about the RECORDS the gateway is holding,
--           not the §2.4 refunded amount, which excludes pending refunds.
--           The question asks WHICH showrooms, so the answer is a SET of showrooms and
--           the shape is a LIST: membership decides correctness and order does not
--           (docs/M2_NOTES.md §5). The value carried is how many records each holds,
--           which is the natural figure alongside the name.
--           A showroom with NO pending refunds is NOT in the answer. That is not the
--           zero-row trap of docs/M2_NOTES.md §5 -- the question asks which showrooms
--           have them, so absence is the answer for that showroom rather than a value
--           of zero that went missing.
--           "Still pending" is a SNAPSHOT as at the reporting date with no lower bound,
--           the same posture as unsettled amount (§2.14). No record ages out, however
--           old it is.
--           The showroom is the one the refunded ORDER was placed at, reached through
--           the order; refunds carry no geography of their own.
--           Membership of the pending set is the gateway's, recorded at construction in
--           truth/constructed.json (D11); this query computes the warehouse's mirror of
--           it, and the isolated run checks the two agree.
-- excludes: test transactions, via the joined order (refunds carry no flag of their own)
select s.name as key,
       count(*) as value
from refunds rf
join orders o on o.order_id = rf.order_id
join showrooms s on s.showroom_id = o.showroom_id
where not o.is_test
  and rf.status = 'pending'
  and s.region_id = 'IN-TN'
group by s.name
order by key asc
