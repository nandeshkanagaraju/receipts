-- qid:      DV-009
-- value:    ratio
-- shape:    ranking
-- window:   last_7_days        -> 2026-09-03 .. 2026-09-09   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   failure rate by reason (§2.10)
-- scope:    city Chennai
-- currency: none
-- top_k:    5
-- rule:     the denominator is ALL attempts in the window, of any outcome --
--           captured and failed alike -- not the number of failed attempts
--           (§2.10). The rates therefore sum to the overall attempt failure
--           rate, NOT to 100%. A set of per-reason figures summing to 100% has
--           been computed against the wrong denominator.
--           "The last 7 days" is the seven days ending YESTERDAY; the reporting
--           day is excluded because it is not over (§1.6a).
-- excludes: test attempts (§1.1)
with scoped as (
    select a.failure_reason
    from payment_attempts a
    join orders o on o.order_id = a.order_id
    join showrooms s on s.showroom_id = o.showroom_id
    join cities ci on ci.city_id = s.city_id
    where not a.is_test
      and ci.name = 'Chennai'
      and a.business_date between date '2026-09-03' and date '2026-09-09'
)
select failure_reason as key,
       cast(count(*) * 1.0 / (select count(*) from scoped) as decimal(38,12)) as value
from scoped
where failure_reason is not null
group by failure_reason
order by value desc, key asc
limit 5
