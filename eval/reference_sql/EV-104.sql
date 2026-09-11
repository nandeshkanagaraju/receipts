-- qid:      EV-104
-- value:    money_minor
-- shape:    ranking
-- window:   july_2026          -> 2026-07-01 .. 2026-07-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   refunded amount (§2.4), by phone model
-- scope:    country GB
-- currency: GBP (§1.4 rule 1 -- "in pounds")
-- top_k:    10
-- rule:     refunds PROCESSED in the window, keyed on refund business date (§2.4);
--           pending and failed refunds are not counted. Partial refunds count for the
--           amount actually refunded (§4.3).
--           Order-level money broken down by a product dimension is attributed ENTIRELY
--           to the order's HANDSET (§1.7a): the whole order value sits against that
--           handset's model, and the accessory lines contribute nothing to the split. It
--           is not an allocation across lines -- every order carries exactly one handset,
--           so nothing needs apportioning.
-- excludes: test transactions via the joined order (refunds carry no flag); pending and failed refunds
with fx as (
    select c.rate_date,
           c.currency,
           cast(c.usd_per_unit / r.usd_per_unit as decimal(38,12)) as to_reporting
    from fx_rates c
    join fx_rates r on r.rate_date = c.rate_date and r.currency = 'GBP'
),
handset as (
    select i.order_id, min(p.model_name) as model_name
    from order_items i join products p on p.sku = i.sku
    where not p.is_accessory group by i.order_id
)
select h.model_name as key,
       cast(round(sum(rf.amount_minor * fx.to_reporting)) as bigint) as value
from refunds rf
join orders o on o.order_id = rf.order_id
join showrooms s on s.showroom_id = o.showroom_id
join handset h on h.order_id = rf.order_id
join fx on fx.currency = rf.currency and fx.rate_date = rf.business_date
where not o.is_test and rf.status = 'processed' and s.country_code = 'GB'
  and rf.business_date between date '2026-07-01' and date '2026-07-31'
group by h.model_name order by value desc, key asc limit 10
