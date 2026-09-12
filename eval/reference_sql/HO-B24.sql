-- qid:      HO-B24
-- value:    money_minor
-- shape:    ranking
-- window:   last_90_days       -> 2026-06-12 .. 2026-09-09   (read as §1.6a reads "last 7 days")
-- metric:   refunded amount (§2.4) by country
-- scope:    all countries
-- currency: USD (§1.4 rule 2 -- global_finance reports in US dollars)
-- top_k:    6
-- rule:     the row carries an `interpretation` because "the last 90 days" is not a
--           window the glossary names, and that sentence governs. It is read exactly as
--           §1.6a reads "the last 7 days": the N days ENDING YESTERDAY, with the
--           reporting day excluded.
--           "Refund value" is the refunded AMOUNT (§2.4, §6.1), not a count of refunds
--           and not a rate. Partial refunds count the amount actually refunded, never
--           the value of the original order (§4.3).
--           Keyed on the REFUND business date -- the local date the refund was
--           processed, not the date of the order being refunded (§2.4, §1.2). A refund
--           issued in September against a June order belongs to September here.
--           Each amount converts at the daily rate for ITS OWN refund business date
--           (§1.3, §2.4, §4.4). Summing raw minor units across six currencies would
--           produce a figure that is not money in any currency.
--           A country with no refunds is an exact zero rather than a missing row
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
      and rf.business_date between date '2026-06-12' and date '2026-09-09'
    group by s.country_code
)
select sp.country_code as key,
       cast(round(coalesce(v.amount, 0)) as bigint) as value
from spine sp
left join valued v on v.country_code = sp.country_code
order by value desc, key asc
limit 6
