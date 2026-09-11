-- qid:      HO-002
-- value:    money_minor
-- shape:    series
-- window:   last_7_days        -> 2026-09-03 .. 2026-09-09   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   refunded amount (§2.4), daily
-- scope:    country GB
-- currency: GBP (§1.4 rule 2 -- store_ops_uk reports in GBP)
-- rule:     a SERIES: matched by time key, not by rank (ADR-009), and carrying no
--           top_k. A rank comparison would pass a result whose days were right but
--           misordered, which for a series is the entire answer.
--           "The last 7 days" is the seven days ending YESTERDAY (§1.6a): the
--           reporting day is excluded because it is not over. This is a different
--           window from "last week" (§1.6).
--           Refunded amount is keyed on the REFUND business date -- the local date
--           the refund was processed, not the date of the order being refunded
--           (§2.4, §1.2). Partial refunds count the amount actually refunded, never
--           the value of the original order (§4.3).
--           Pending and failed refunds are not counted (§2.4); only `processed`.
--           Every day in the window returns a row. A day with no refunds is an exact
--           zero, not a missing row: an empty result and a result of zero are
--           different claims (docs/M2_NOTES.md §5).
--           The scope is one country and one currency, so no conversion arises --
--           §1.3 converts only where a question spans currencies.
-- excludes: test transactions, via the joined order (refunds carry no flag of their
--           own, so the exclusion has to travel through the order)
with days as (
    select cast(d as date) as business_date
    from generate_series(date '2026-09-03', date '2026-09-09', interval 1 day) as t(d)
),
valued as (
    select rf.business_date, sum(rf.amount_minor) as amount
    from refunds rf
    join orders o on o.order_id = rf.order_id
    join showrooms s on s.showroom_id = o.showroom_id
    where not o.is_test
      and rf.status = 'processed'
      and s.country_code = 'GB'
      and rf.business_date between date '2026-09-03' and date '2026-09-09'
    group by rf.business_date
)
select cast(d.business_date as varchar) as key,
       cast(coalesce(v.amount, 0) as bigint) as value
from days d
left join valued v on v.business_date = d.business_date
order by key asc
