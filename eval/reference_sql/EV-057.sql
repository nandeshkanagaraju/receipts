-- qid:      EV-057
-- value:    count
-- shape:    series
-- window:   last_8_weeks       -> 2026-07-13 .. 2026-09-06   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   duplicate capture count (§2.15), weekly
-- scope:    country IN
-- currency: none
-- rule:     FLAG -- THE ROLE ON THIS QUESTION IS store_ops_uk AND THE QUESTION ASKS
--           ABOUT INDIA. Under D7 scope comes from auth context, and the question-set rule
--           is explicit that a manager asking outside their scope must be DENIED
--           (eval/questions/README.md, authoring rule 5). The row is populated ANS. The
--           question file is frozen to this session, so the reference follows the QUESTION
--           TEXT -- India -- and the mismatch is reported rather than silently resolved.
--           See the M3 report.
--           For a PAIR the count is ONE: one capture is legitimate, one is the duplicate;
--           three captures of the same amount count as two (§2.15).
--           Keyed on the capture business date of the DUPLICATE capture (§2.15).
--           "Last 8 weeks" is eight COMPLETE Monday-Sunday weeks; the current partial week
--           is excluded, not counted as one of the eight (§1.6a).
--           A week with no duplicates is an exact zero, not a missing row -- so the series
--           is built from the eight week starts and left-joined.
-- excludes: test transactions (§1.1)
with weeks as (
    select cast(date '2026-07-13' + cast(n * 7 as integer) as date) as week_start
    from range(0, 8) t(n)
),
dups as (
    select c.business_date
    from (
        select a.order_id, a.business_date,
               row_number() over (
                   partition by a.order_id, a.amount_minor
                   order by a.attempt_no, a.attempt_id
               ) as capture_rank
        from payment_attempts a
        where a.status = 'captured' and not a.is_test
    ) c
    join orders o on o.order_id = c.order_id
    join showrooms s on s.showroom_id = o.showroom_id
    where c.capture_rank > 1 and s.country_code = 'IN'
      and c.business_date between date '2026-07-13' and date '2026-09-06'
)
select cast(w.week_start as varchar) as key,
       count(dups.business_date) as value
from weeks w
left join dups on cast(date_trunc('week', dups.business_date) as date) = w.week_start
group by w.week_start order by key asc
