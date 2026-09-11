-- qid:      EV-100
-- value:    money_minor
-- shape:    scalar
-- window:   pending_as_at_as_of -> 2025-03-01 .. 2026-09-09   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   refunds still pending at the gateway (§6.3), summed
-- scope:    all countries
-- currency: USD (§1.4 rule 1 -- the asker named it)
-- rule:     §6.3 -- in a gateway question "refunds" means the records the gateway is
--           holding. This one asks for their VALUE, so the records are summed; it is NOT
--           the §2.4 refunded amount, which counts refunds PROCESSED in a window and
--           explicitly excludes pending ones.
--           "Still pending" is a snapshot as at the reporting date with no lower bound --
--           the same posture as unsettled amount (§2.14). No record ages out.
--           Each amount converts at the daily rate for its own refund business date, so
--           the multi-currency rule holds across all six countries (§1.3, §4.4).
-- excludes: test transactions via the joined order (refunds carry no flag)
with fx as (
    select c.rate_date,
           c.currency,
           cast(c.usd_per_unit / r.usd_per_unit as decimal(38,12)) as to_reporting
    from fx_rates c
    join fx_rates r on r.rate_date = c.rate_date and r.currency = 'USD'
)
select cast(round(sum(rf.amount_minor * fx.to_reporting)) as bigint) as value
from refunds rf
join orders o on o.order_id = rf.order_id
join fx on fx.currency = rf.currency and fx.rate_date = rf.business_date
where not o.is_test and rf.status = 'pending'
order by value
