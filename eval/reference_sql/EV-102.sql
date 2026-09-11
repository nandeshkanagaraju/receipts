-- qid:      EV-102
-- value:    money_minor
-- shape:    ranking
-- window:   july_2026          -> 2026-07-01 .. 2026-07-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   net revenue (§2.5), by phone model
-- scope:    country AE
-- currency: AED (§1.4 rule 1 -- "in dirhams")
-- top_k:    10
-- rule:     Order-level money broken down by a product dimension is attributed ENTIRELY
--           to the order's HANDSET (§1.7a): the whole order value sits against that
--           handset's model, and the accessory lines contribute nothing to the split. It
--           is not an allocation across lines -- every order carries exactly one handset,
--           so nothing needs apportioning.
--           Net revenue is captured GMV minus refunds PROCESSED in the same window (§2.5);
--           each refund is attributed to its own order's handset by the same rule.
--           A model can be negative for a narrow window; that is a real result (§2.5).
-- excludes: test transactions (§1.1); pending and failed refunds; duplicate captures
with fx as (
    select c.rate_date,
           c.currency,
           cast(c.usd_per_unit / r.usd_per_unit as decimal(38,12)) as to_reporting
    from fx_rates c
    join fx_rates r on r.rate_date = c.rate_date and r.currency = 'AED'
),
captures as (
    select a.order_id, a.amount_minor, a.currency, a.business_date,
           row_number() over (
               partition by a.order_id, a.amount_minor
               order by a.attempt_no, a.attempt_id
           ) as capture_rank
    from payment_attempts a
    join orders o on o.order_id = a.order_id
    join showrooms s on s.showroom_id = o.showroom_id
    where a.status = 'captured'
      and not a.is_test
      and not o.is_test
      and s.country_code = 'AE'
      and a.business_date between date '2026-07-01' and date '2026-07-31'
),
handset as (
    select i.order_id, min(p.model_name) as model_name
    from order_items i join products p on p.sku = i.sku
    where not p.is_accessory group by i.order_id
),
captured as (
    select h.model_name, sum(c.amount_minor * fx.to_reporting) as amount
    from captures c
    join fx on fx.currency = c.currency and fx.rate_date = c.business_date
    join handset h on h.order_id = c.order_id
    where c.capture_rank = 1 group by h.model_name
),
refunded as (
    select h.model_name, sum(rf.amount_minor * fx.to_reporting) as amount
    from refunds rf
    join orders o on o.order_id = rf.order_id
    join showrooms s on s.showroom_id = o.showroom_id
    join handset h on h.order_id = rf.order_id
    join fx on fx.currency = rf.currency and fx.rate_date = rf.business_date
    where not o.is_test and rf.status = 'processed' and s.country_code = 'AE'
      and rf.business_date between date '2026-07-01' and date '2026-07-31'
    group by h.model_name
)
select captured.model_name as key,
       cast(round(captured.amount - coalesce(refunded.amount, 0)) as bigint) as value
from captured left join refunded on refunded.model_name = captured.model_name
order by value desc, key asc limit 10
