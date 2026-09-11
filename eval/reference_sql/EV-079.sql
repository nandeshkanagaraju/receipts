-- qid:      EV-079
-- value:    money_minor
-- shape:    ranking
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   refunded amount (§2.4), by city
-- scope:    region IN-TN (Tamil Nadu)
-- currency: INR (§1.4 rule 1 -- "in rupees")
-- top_k:    10
-- rule:     refunds PROCESSED in the window; pending and failed are not counted (§2.4).
--           Keyed on refund business date, NOT the date of the order being refunded
--           (§1.2): a refund in August against a July capture belongs to August here and
--           to July for revenue, and both are correct.
--           Partial refunds count for the amount actually refunded (§4.3).
-- excludes: test transactions via the joined order (refunds carry no flag); pending and failed refunds
with fx as (
    select c.rate_date,
           c.currency,
           cast(c.usd_per_unit / r.usd_per_unit as decimal(38,12)) as to_reporting
    from fx_rates c
    join fx_rates r on r.rate_date = c.rate_date and r.currency = 'INR'
)
select ci.name as key,
       cast(round(sum(rf.amount_minor * fx.to_reporting)) as bigint) as value
from refunds rf
join orders o on o.order_id = rf.order_id
join showrooms s on s.showroom_id = o.showroom_id
join cities ci on ci.city_id = s.city_id
join fx on fx.currency = rf.currency and fx.rate_date = rf.business_date
where not o.is_test and rf.status = 'processed' and s.region_id = 'IN-TN'
  and rf.business_date between date '2026-08-01' and date '2026-08-31'
group by ci.name order by value desc, key asc limit 10
