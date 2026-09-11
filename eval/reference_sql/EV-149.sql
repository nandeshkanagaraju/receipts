-- qid:      EV-149
-- value:    money_minor
-- shape:    list
-- window:   july_2026          -> 2026-07-01 .. 2026-07-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   refunds still pending at the gateway (§6.3)
-- scope:    city Chennai
-- currency: INR (§1.4 rule 2 -- rm_tamil_nadu reports in INR)
-- source:   gateway
-- rule:     §6.3 -- in a gateway question "refunds" means the RECORDS the gateway is
--           holding. The question is a yes/no in English, but the useful answer is WHICH,
--           so the reference is the list and is compared as a SET (docs/M2_NOTES.md §5).
--           An EMPTY list is a legitimate answer here and means "no": it is not a missing
--           result and there is no row containing 0 that would say it.
--           "Refunds from July" keys on the refund's CREATION business date. A pending
--           refund has no processed date, which is exactly why refund age is defined on
--           creation (§2.4a).
--           Membership comes from truth/constructed.json (D11); this query is the
--           warehouse mirror and evalkit.reference requires the two to agree.
-- excludes: test transactions via the joined order (refunds carry no flag)
with fx as (
    select c.rate_date,
           c.currency,
           cast(c.usd_per_unit / r.usd_per_unit as decimal(38,12)) as to_reporting
    from fx_rates c
    join fx_rates r on r.rate_date = c.rate_date and r.currency = 'INR'
)
select rf.refund_id as key,
       cast(round(rf.amount_minor * fx.to_reporting) as bigint) as value
from refunds rf
join orders o on o.order_id = rf.order_id
join showrooms s on s.showroom_id = o.showroom_id
join cities ci on ci.city_id = s.city_id
join fx on fx.currency = rf.currency and fx.rate_date = rf.business_date
where not o.is_test and rf.status = 'pending' and ci.name = 'Chennai'
  and rf.business_date between date '2026-07-01' and date '2026-07-31'
order by key asc
