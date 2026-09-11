-- qid:      EV-025
-- value:    money_minor
-- shape:    ranking
-- window:   july_2026          -> 2026-07-01 .. 2026-07-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   NOT a governed dimension -- refunded amount (§2.4) by refund reason
-- scope:    country AE
-- currency: AED (§1.4 rule 1 -- "in the UAE ... in dirhams" is the named currency)
-- top_k:    5
-- rule:     interpretation: "sum of processed non-test refund amounts at UAE showrooms
--           in the window, grouped by the refund's reason field, keyed on refund business
--           date, in AED. Refund reason is not an allowed dimension in the glossary."
--           The METRIC is refunded amount (§2.4) and follows it exactly: refunds PROCESSED
--           in the window, pending and failed excluded, partial refunds counted for the
--           amount actually refunded (§4.3), keyed on refund business date and not on the
--           date of the order being refunded (§1.2). Only the breakdown is ungoverned.
-- excludes: test transactions via the joined order (refunds carry no flag); pending and failed refunds
with fx as (
    select c.rate_date,
           c.currency,
           cast(c.usd_per_unit / r.usd_per_unit as decimal(38,12)) as to_reporting
    from fx_rates c
    join fx_rates r on r.rate_date = c.rate_date and r.currency = 'AED'
)
select rf.reason as key,
       cast(round(sum(rf.amount_minor * fx.to_reporting)) as bigint) as value
from refunds rf
join orders o on o.order_id = rf.order_id
join showrooms s on s.showroom_id = o.showroom_id
join fx on fx.currency = rf.currency and fx.rate_date = rf.business_date
where not o.is_test and rf.status = 'processed' and s.country_code = 'AE'
  and rf.business_date between date '2026-07-01' and date '2026-07-31'
group by rf.reason order by value desc, key asc limit 5
