-- qid:      DV-022
-- value:    count
-- shape:    scalar
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   duplicate capture count (§2.15)
-- scope:    region IN-TN (Tamil Nadu)
-- currency: none
-- rule:     for a PAIR of duplicate captures the count is ONE -- one capture is
--           legitimate and one is the duplicate; three captures of the same
--           amount count as two (§2.15). So the count is captures beyond the
--           first on the same order for the same amount.
--           Keyed on the capture business date of the DUPLICATE capture.
--           Duplicates are counted once in captured GMV so revenue is not
--           overstated, and surfaced here so the operational fault is not
--           hidden (§4.10).
-- excludes: test transactions (§1.1)
with captures as (
    select a.order_id, a.business_date,
           row_number() over (
               partition by a.order_id, a.amount_minor
               order by a.attempt_no, a.attempt_id
           ) as capture_rank
    from payment_attempts a
    where a.status = 'captured'
      and not a.is_test
)
select count(*) as value
from captures c
join orders o on o.order_id = c.order_id
join showrooms s on s.showroom_id = o.showroom_id
where c.capture_rank > 1
  and s.region_id = 'IN-TN'
  and c.business_date between date '2026-08-01' and date '2026-08-31'
