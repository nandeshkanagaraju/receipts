-- qid:      HO-008
-- value:    money_minor
-- shape:    scalar
-- window:   last_7_days        -> 2026-09-03 .. 2026-09-09   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   captured GMV (§2.3)
-- scope:    region IN-TN (Tamil Nadu)
-- currency: INR (§1.4 rule 1 -- the asker named it)
-- rule:     "The last 7 days" is the seven days ending YESTERDAY (§1.6a): the
--           reporting day is excluded because it is not over, and including a partial
--           day understates that day's figure. It is NOT the same window as "last
--           week" (§1.6).
--           Each day is the SHOWROOM'S OWN LOCAL business date (§1.7, §4.5). In India
--           the offset is five and a half hours, so a UTC-day query would start at
--           5:30 a.m. Chennai time, drop the previous evening's trade and add the
--           current morning's. The local business date is stored on every fact row
--           and is the only key used here.
--           Captured money only, never authorised (§2.3, §4.2); the duplicate side of
--           a duplicate capture is counted once (§4.10).
--           The scope is one region and one currency, so no conversion arises (§1.3).
-- excludes: test orders and test attempts (§1.1); duplicate captures
with captures as (
    select a.order_id, a.amount_minor, a.business_date,
           row_number() over (
               partition by a.order_id, a.amount_minor
               order by a.attempt_no, a.attempt_id
           ) as capture_rank
    from payment_attempts a
    where a.status = 'captured'
      and not a.is_test
)
select cast(sum(c.amount_minor) as bigint) as value
from captures c
join orders o on o.order_id = c.order_id
join showrooms s on s.showroom_id = o.showroom_id
where c.capture_rank = 1
  and not o.is_test
  and s.region_id = 'IN-TN'
  and c.business_date between date '2026-09-03' and date '2026-09-09'
order by value
