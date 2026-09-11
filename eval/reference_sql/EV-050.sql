-- qid:      EV-050
-- value:    days
-- shape:    list
-- window:   age_over_14_days   -> 2025-03-01 .. 2026-08-26   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   refund age (§2.4a) over pending gateway refunds (§6.3)
-- scope:    country GB
-- currency: GBP (§1.4 rule 2 -- store_ops_uk reports in GBP); not used, the value is days
-- source:   gateway
-- rule:     refund age is the REPORTING DATE minus the refund's CREATION business date,
--           in whole days (§2.4a) -- not the processed date. An unprocessed refund has no
--           processed date, and age is precisely the question one asks about refunds that
--           have not completed.
--           "More than 14 days old" means age >= 15, so created on or before 2026-08-26,
--           which is as_of minus 15 days. The boundary is derived from as_of, never from
--           a clock (§1.7, D2).
--           §6.3: a gateway question asks for RECORDS, so this is a LIST compared as a
--           SET (docs/M2_NOTES.md §5). Membership comes from truth/constructed.json (D11)
--           and evalkit.reference requires the warehouse mirror to agree.
-- excludes: test transactions via the joined order (refunds carry no flag)
select rf.refund_id as key,
       cast(date '2026-09-10' - rf.business_date as bigint) as value
from refunds rf
join orders o on o.order_id = rf.order_id
join showrooms s on s.showroom_id = o.showroom_id
where not o.is_test and rf.status = 'pending' and s.country_code = 'GB'
  and rf.business_date <= date '2026-08-26'
order by key asc
