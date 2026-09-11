-- qid:      EV-067
-- value:    money_minor
-- shape:    series
-- window:   last_8_weeks       -> 2026-07-13 .. 2026-09-06   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   refunded amount (§2.4), weekly
-- scope:    country AE
-- currency: AED (§1.4 rule 1 -- "in dirhams")
-- rule:     refunds PROCESSED in the window (§2.4); pending and failed refunds are not
--           counted -- money that has not gone back has not been refunded.
--           Keyed on refund business date, NOT the date of the order being refunded
--           (§1.2). Partial refunds count for the amount actually refunded (§4.3).
--           Eight COMPLETE Monday-Sunday weeks; the current partial week is excluded, not
--           counted as one of the eight (§1.6a). A series is matched by time key.
-- excludes: test transactions via the joined order (refunds carry no flag); pending and failed refunds
with fx as (
    select c.rate_date,
           c.currency,
           cast(c.usd_per_unit / r.usd_per_unit as decimal(38,12)) as to_reporting
    from fx_rates c
    join fx_rates r on r.rate_date = c.rate_date and r.currency = 'AED'
)
select cast(cast(date_trunc('week', rf.business_date) as date) as varchar) as key,
       cast(round(sum(rf.amount_minor * fx.to_reporting)) as bigint) as value
from refunds rf
join orders o on o.order_id = rf.order_id
join showrooms s on s.showroom_id = o.showroom_id
join fx on fx.currency = rf.currency and fx.rate_date = rf.business_date
where not o.is_test and rf.status = 'processed' and s.country_code = 'AE'
  and rf.business_date between date '2026-07-13' and date '2026-09-06'
group by key order by key asc
