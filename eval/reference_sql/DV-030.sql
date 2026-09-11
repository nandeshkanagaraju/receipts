-- qid:      DV-030
-- value:    money_minor
-- shape:    scalar
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   refunded amount (§2.4)
-- scope:    country GB
-- currency: GBP (§1.4 rule 2 -- store_ops_uk reports in GBP)
-- rule:     refunds PROCESSED in the window (§2.4). Pending and failed refunds
--           are not counted -- money that has not gone back has not been
--           refunded.
--           Partial refunds count for the amount ACTUALLY refunded, not the
--           value of the original order (§4.3): a customer returning one item
--           of three is not a fully refunded order.
--           Keyed on refund business date, NOT the date of the order being
--           refunded (§1.2). A refund in August against a July capture belongs
--           to August here and to July for revenue; both are correct.
-- excludes: test transactions via the joined order (refunds carry no flag);
--           pending and failed refunds
with fx as (
    select c.rate_date,
           c.currency,
           cast(c.usd_per_unit / r.usd_per_unit as decimal(38,12)) as to_reporting
    from fx_rates c
    join fx_rates r on r.rate_date = c.rate_date and r.currency = 'GBP'
)
select cast(round(coalesce(sum(rf.amount_minor * fx.to_reporting), 0)) as bigint) as value
from refunds rf
join orders o on o.order_id = rf.order_id
join showrooms s on s.showroom_id = o.showroom_id
join fx on fx.currency = rf.currency and fx.rate_date = rf.business_date
where not o.is_test
  and rf.status = 'processed'
  and s.country_code = 'GB'
  and rf.business_date between date '2026-08-01' and date '2026-08-31'
order by value
