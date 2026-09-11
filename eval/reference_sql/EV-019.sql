-- qid:      EV-019
-- value:    ratio
-- shape:    ranking
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   failure rate by reason (§2.10)
-- scope:    country US
-- currency: none
-- top_k:    5
-- rule:     the denominator is ALL attempts in the window, of ANY outcome -- captured
--           and failed alike -- NOT the number of failed attempts (§2.10).
--           So these rates sum to the overall attempt failure rate, NOT to 100%. A set of
--           per-reason figures summing to 100% has been computed against the wrong
--           denominator: that is the share OF FAILURES by reason, a different and
--           undefined quantity at Kestrel.
-- excludes: test attempts (§1.1)
with scoped as (
    select a.failure_reason
    from payment_attempts a
    join orders o on o.order_id = a.order_id
    join showrooms s on s.showroom_id = o.showroom_id
    where not a.is_test and s.country_code = 'US'
      and a.business_date between date '2026-08-01' and date '2026-08-31'
)
select failure_reason as key,
       cast(count(*) * 1.0 / (select count(*) from scoped) as decimal(38,12)) as value
from scoped where failure_reason is not null
group by failure_reason order by value desc, key asc limit 5
