-- qid:      HO-B23
-- value:    count
-- shape:    ranking
-- window:   this_month_to_date -> 2026-09-01 .. 2026-09-09   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   a count of failed attempts -- NOT a glossary metric; the row's
--           `interpretation` governs (ADR-009)
-- scope:    all countries, method card
-- currency: none (a count)
-- top_k:    10
-- rule:     the row carries an `interpretation` because §2.10 defines the failure RATE
--           by reason, whose denominator is ALL attempts, and says explicitly that a
--           plain COUNT of failures is legitimate but undefined here. The question asks
--           for "the most declined", which is a count.
--           A count, not a rate: a bank with many attempts will head this ranking
--           whether or not it declines an unusual SHARE of them, and the two orderings
--           are different. §2.10's warning about per-reason rates summing to the overall
--           failure rate rather than to 100% is the same confusion in another shape.
--           ATTEMPT-level throughout: every attempt carries its own method and issuing
--           bank, so no attribution rule is needed (§1.9, last paragraph). This is not an
--           order-level figure and must not be compared with one (§4.1).
--           "Declined" is `status = 'failed'`. It deliberately does NOT include
--           `authorized` attempts that were never captured: an authorisation SUCCEEDED,
--           and since ADR-014 those rows inherit the failure distribution, so counting
--           them as declines by bank would read a planted anomaly as bank behaviour
--           (ADR-014, LIMITATIONS.md).
--           "This month" is month-to-date and ends YESTERDAY (§1.6a, §5.4).
--           Keyed on attempt business date (§2.10).
-- excludes: test attempts and test orders (§1.1); attempts with no issuing bank
select a.issuing_bank as key,
       count(*) as value
from payment_attempts a
join orders o on o.order_id = a.order_id
where not a.is_test
  and not o.is_test
  and a.method = 'card'
  and a.status = 'failed'
  and a.issuing_bank is not null
  and a.business_date between date '2026-09-01' and date '2026-09-09'
group by a.issuing_bank
order by value desc, key asc
limit 10
