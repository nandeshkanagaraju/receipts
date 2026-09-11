-- qid:      HO-027
-- value:    count
-- shape:    scalar
-- window:   pending_as_at_as_of -> 2025-03-01 .. 2026-09-09   (a snapshot, as_of 2026-09-10)
-- metric:   refunds still pending at the gateway (§6.3), counted
-- scope:    all countries, orders paid by card
-- currency: none (a count)
-- rule:     §6.3 -- in a gateway question "refunds" means the RECORDS the gateway is
--           holding, not the §2.4 refunded amount, which counts refunds PROCESSED in a
--           window and explicitly excludes pending ones. This question asks how MANY
--           records, so the answer is a count.
--           "Still pending" is a SNAPSHOT as at the reporting date with no lower
--           bound -- the same posture as unsettled amount (§2.14). No record ages out,
--           however old it is.
--           "Card-paid orders" means orders whose CAPTURED attempt used card (§5.3a,
--           §6.1) -- the method the money actually came in on. This is deliberately
--           NOT §1.9's "tried" rule, which governs success rates only: an order that
--           tried card, failed, and paid by UPI is not a card order here.
--           An order that was never captured has no paying method and is in no
--           method-qualified set at all (§5.3a).
--           Membership of the pending set is the gateway's, recorded at construction in
--           truth/constructed.json (D11); this query computes the warehouse's mirror of
--           it, and the isolated run checks the two agree.
-- excludes: test transactions, via the joined order (refunds carry no flag of their own)
with captures as (
    select a.order_id, a.amount_minor, a.method,
           row_number() over (
               partition by a.order_id, a.amount_minor
               order by a.attempt_no, a.attempt_id
           ) as capture_rank
    from payment_attempts a
    where a.status = 'captured'
      and not a.is_test
),
card_paid as (
    select distinct c.order_id
    from captures c
    where c.capture_rank = 1
      and c.method = 'card'
)
select count(*) as value
from refunds rf
join orders o on o.order_id = rf.order_id
join card_paid cp on cp.order_id = rf.order_id
where not o.is_test
  and rf.status = 'pending'
order by value
