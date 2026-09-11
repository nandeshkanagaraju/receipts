-- qid:      EV-130
-- value:    ratio
-- shape:    ranking
-- window:   last_week          -> 2026-08-31 .. 2026-09-06   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   failure rate by reason (§2.10), for UPI
-- scope:    region IN-TN (Tamil Nadu), UPI attempts only
-- currency: none
-- top_k:    5
-- rule:     the denominator is ALL UPI attempts in the window, of ANY outcome (§2.10) --
--           not the number of failed UPI attempts. The rates sum to UPI's overall attempt
--           failure rate, NOT to 100%.
--           Attempt-level, so no attribution rule is needed: every attempt carries its own
--           method (§1.9).
--           "Last week" is the most recent complete Monday-Sunday week (§1.6).
-- excludes: test attempts (§1.1)
with scoped as (
    select a.failure_reason
    from payment_attempts a
    join orders o on o.order_id = a.order_id
    join showrooms s on s.showroom_id = o.showroom_id
    where not a.is_test and a.method = 'upi' and s.region_id = 'IN-TN'
      and a.business_date between date '2026-08-31' and date '2026-09-06'
)
select failure_reason as key,
       cast(count(*) * 1.0 / (select count(*) from scoped) as decimal(38,12)) as value
from scoped where failure_reason is not null
group by failure_reason order by value desc, key asc limit 5
