-- qid:      HO-041
-- value:    money_minor
-- shape:    ranking
-- window:   last_7_days        -> 2026-09-03 .. 2026-09-09   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   refunded amount (§2.4) by country
-- scope:    all countries
-- currency: USD (§1.4 rule 1 -- the asker named it)
-- top_k:    6
-- rule:     "The last 7 days" is the seven days ending YESTERDAY (§1.6a): the reporting
--           day is excluded because it is not over. It is NOT "last week" (§1.6).
--           Refunded amount keys on the REFUND business date -- the local date the
--           refund was PROCESSED, not the date of the order being refunded (§2.4, §1.2).
--           A refund issued in September against an August order belongs to September
--           for refund metrics and to August for revenue metrics; both are correct, and
--           they answer different questions.
--           Partial refunds count the amount actually refunded, never the value of the
--           original order (§4.3).
--           Each amount converts at the daily rate for ITS OWN refund business date
--           (§1.3, §2.4, §4.4). Summing the raw stored minor units across six
--           currencies would produce a figure that is not money in any currency -- and
--           it would look entirely plausible.
--           A country with no refunds in the window is an exact zero, not a missing row
--           (docs/M2_NOTES.md §5).
-- excludes: test transactions, via the joined order (refunds carry no flag of their
--           own); pending and failed refunds (§2.4)
with fx as (
    select c.rate_date,
           c.currency,
           cast(c.usd_per_unit / r.usd_per_unit as decimal(38,12)) as to_reporting
    from fx_rates c
    join fx_rates r on r.rate_date = c.rate_date and r.currency = 'USD'
),
spine as (
    select country_code from countries
),
valued as (
    select s.country_code, sum(rf.amount_minor * fx.to_reporting) as amount
    from refunds rf
    join orders o on o.order_id = rf.order_id
    join showrooms s on s.showroom_id = o.showroom_id
    join fx on fx.currency = rf.currency and fx.rate_date = rf.business_date
    where not o.is_test
      and rf.status = 'processed'
      and rf.business_date between date '2026-09-03' and date '2026-09-09'
    group by s.country_code
)
select sp.country_code as key,
       cast(round(coalesce(v.amount, 0)) as bigint) as value
from spine sp
left join valued v on v.country_code = sp.country_code
order by value desc, key asc
limit 6
