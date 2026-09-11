-- qid:      EV-105
-- value:    money_minor
-- shape:    ranking
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   average order value (§2.6), by phone model
-- scope:    country MY
-- currency: MYR (§1.4 rule 1 -- "in ringgit")
-- top_k:    10
-- rule:     captured GMV over distinct PAID orders, both keyed on capture business date
--           (§2.6). Abandoned and cancelled orders are in neither side.
--           Order-level money broken down by a product dimension is attributed ENTIRELY
--           to the order's HANDSET (§1.7a): the whole order value sits against that
--           handset's model, and the accessory lines contribute nothing to the split. It
--           is not an allocation across lines -- every order carries exactly one handset,
--           so nothing needs apportioning.
--           For EMI orders the value is the full order value, not the instalment (§4.9) --
--           and Malaysia is one of the two countries where EMI exists (§2.11).
-- excludes: test transactions (§1.1); duplicate captures
with fx as (
    select c.rate_date,
           c.currency,
           cast(c.usd_per_unit / r.usd_per_unit as decimal(38,12)) as to_reporting
    from fx_rates c
    join fx_rates r on r.rate_date = c.rate_date and r.currency = 'MYR'
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
      and s.country_code = 'MY'
      and a.business_date between date '2026-08-01' and date '2026-08-31'
),
handset as (
    select i.order_id, min(p.model_name) as model_name
    from order_items i join products p on p.sku = i.sku
    where not p.is_accessory group by i.order_id
)
select h.model_name as key,
       cast(round(
           sum(c.amount_minor * fx.to_reporting) / count(distinct c.order_id)
       ) as bigint) as value
from captures c
join fx on fx.currency = c.currency and fx.rate_date = c.business_date
join handset h on h.order_id = c.order_id
where c.capture_rank = 1 group by h.model_name order by value desc, key asc limit 10
