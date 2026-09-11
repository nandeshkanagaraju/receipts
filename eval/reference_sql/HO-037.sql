-- qid:      HO-037
-- value:    money_minor
-- shape:    scalar
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   refunds against orders captured more than once -- NOT a glossary metric;
--           the row's `interpretation` governs (ADR-009)
-- scope:    region IN-TN (Tamil Nadu)
-- currency: INR (§1.4 rule 1 -- the asker named it)
-- rule:     the row carries an `interpretation` because §2.15 counts duplicate captures
--           and §2.4 totals refunds but the glossary defines no join between them, and
--           that sentence governs.
--           The refund side is §2.4: refunds PROCESSED in the window, at the amount
--           actually refunded, keyed on REFUND business date (§4.3). Pending and failed
--           refunds are not counted.
--           The order qualifies when it has MORE THAN ONE captured payment attempt AT
--           ANY TIME -- the interpretation says so explicitly, so the duplicate capture
--           need not fall inside the window. A duplicate captured in July and refunded
--           in August belongs here, which is the ordinary sequence: §2.15 notes that
--           duplicates are refunded once noticed, so the refund almost always lands
--           after the capture.
--           The qualifying test counts CAPTURED attempts on the order, which is the
--           interpretation's wording, rather than §2.15's same-amount pairing. Since
--           ADR-014 an `authorized` attempt is not a capture and does not qualify an
--           order (§4.2).
--           The scope is one region and one currency, so no conversion arises (§1.3).
-- excludes: test orders and test attempts (§1.1); pending and failed refunds (§2.4)
with captured_counts as (
    select a.order_id, count(*) as captures
    from payment_attempts a
    where a.status = 'captured'
      and not a.is_test
    group by a.order_id
),
duplicated as (
    select order_id from captured_counts where captures > 1
)
select cast(coalesce(sum(rf.amount_minor), 0) as bigint) as value
from refunds rf
join orders o on o.order_id = rf.order_id
join showrooms s on s.showroom_id = o.showroom_id
join duplicated d on d.order_id = rf.order_id
where not o.is_test
  and rf.status = 'processed'
  and s.region_id = 'IN-TN'
  and rf.business_date between date '2026-08-01' and date '2026-08-31'
order by value
