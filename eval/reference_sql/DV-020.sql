-- qid:      DV-020
-- value:    money_minor
-- shape:    list
-- window:   last_week          -> 2026-08-31 .. 2026-09-06   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   refunds still pending at the gateway (§6.3, §2.4a)
-- scope:    country GB
-- currency: GBP (§1.4 rule 2 -- store_ops_uk reports in GBP)
-- source:   gateway
-- rule:     §6.3 -- a gateway question asks for RECORDS, not a total, so the
--           answer is a list and is compared as a SET: membership decides
--           correctness, order does not (docs/M2_NOTES.md §5). "Refunds from
--           last week" keys on the refund's CREATION business date: a pending
--           refund has no processed date (§2.4a), which is precisely why age is
--           defined on creation.
--           Membership is decided by truth/constructed.json, written at
--           construction (D11); this query computes the warehouse's mirror of
--           it and evalkit.reference requires the two to agree.
-- excludes: test transactions, via the joined order (refunds carry no flag)
with fx as (
    select c.rate_date,
           c.currency,
           cast(c.usd_per_unit / r.usd_per_unit as decimal(38,12)) as to_reporting
    from fx_rates c
    join fx_rates r on r.rate_date = c.rate_date and r.currency = 'GBP'
)
select rf.refund_id as key,
       cast(round(rf.amount_minor * fx.to_reporting) as bigint) as value
from refunds rf
join orders o on o.order_id = rf.order_id
join showrooms s on s.showroom_id = o.showroom_id
join fx on fx.currency = rf.currency and fx.rate_date = rf.business_date
where not o.is_test
  and rf.status = 'pending'
  and s.country_code = 'GB'
  and rf.business_date between date '2026-08-31' and date '2026-09-06'
order by key asc
