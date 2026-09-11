-- qid:      EV-124
-- value:    ratio
-- shape:    ranking
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   attempt-level failure rate, by issuing bank (§2.10's denominator rule, §2.9's grain)
-- scope:    country IN
-- currency: none
-- top_k:    10
-- rule:     the denominator is ALL attempts on that bank, of ANY outcome -- captured and
--           failed alike -- not the number of failed attempts (§2.10). A set of figures
--           summing to 100% has been computed against the wrong denominator.
--           This is ATTEMPT-level, so no attribution rule is needed: every attempt already
--           carries its own issuing bank (§1.9). Contrast EV-114, an order-level success
--           rate by bank, which does need the "tried" rule and whose denominators overlap.
--           ISSUING bank is the customer's; acquiring is Kestrel's (§1.9).
-- excludes: test attempts (§1.1)
select a.issuing_bank as key,
       cast(
           sum(case when a.status = 'failed' then 1 else 0 end) * 1.0 / count(*)
       as decimal(38,12)) as value
from payment_attempts a
join orders o on o.order_id = a.order_id
join showrooms s on s.showroom_id = o.showroom_id
where not a.is_test and a.issuing_bank is not null and s.country_code = 'IN'
  and a.business_date between date '2026-08-01' and date '2026-08-31'
group by a.issuing_bank order by value desc, key asc limit 10
