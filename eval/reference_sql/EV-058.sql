-- qid:      EV-058
-- value:    ratio
-- shape:    scalar
-- window:   august_2026        -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   NOT a Kestrel metric -- duplicate capture SHARE, per the row's `interpretation`
-- scope:    country IN
-- currency: none
-- rule:     interpretation: "count of non-test captured attempts that duplicate another
--           capture on the same order, divided by all non-test captured attempts, at
--           Indian showrooms in the window, keyed on capture business date. Neither the
--           ratio nor its denominator is defined in the glossary."
--           §2.15 defines the COUNT; turning it into a share needs a denominator the
--           glossary never names, which is why this row is annotated.
--           For a PAIR the numerator counts ONE -- one capture is legitimate, one is the
--           duplicate (§2.15). The denominator is every capture, duplicates included.
--           This is a near-zero metric almost everywhere, which is why it is asked as a
--           scalar rather than as a ranking (docs/M2_NOTES.md §5).
-- excludes: test transactions (§1.1)
with captures as (
    select a.order_id, a.amount_minor, a.currency, a.business_date,
           row_number() over (
               partition by a.order_id, a.amount_minor
               order by a.attempt_no, a.attempt_id
           ) as capture_rank
    from payment_attempts a
    join orders o on o.order_id = a.order_id
    join showrooms s on s.showroom_id = o.showroom_id
    where a.status = 'captured'
      and not a.is_test
      and not o.is_test
      and s.country_code = 'IN'
      and a.business_date between date '2026-08-01' and date '2026-08-31'
)
select cast(
           sum(case when c.capture_rank > 1 then 1 else 0 end) * 1.0 / count(*)
       as decimal(38,12)) as value
from captures c
