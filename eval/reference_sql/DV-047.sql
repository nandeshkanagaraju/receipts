-- qid:      DV-047
-- value:    ratio
-- shape:    ranking
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   refund rate (§2.7), by phone model, for card-paid orders
-- scope:    country AE, card-paid orders only
-- currency: USD (§1.4 rule 2 -- global_finance reports in USD); both sides
--           converted before dividing (§2.7)
-- top_k:    10
-- rule:     refund rate is VALUE-based (§2.7): refunded amount over captured
--           GMV. Each side keeps its own date key -- refunds on refund business
--           date, captures on capture business date -- so the two sides do not
--           describe the same orders (§2.7). Partial refunds count for the
--           amount actually refunded (§4.3).
--           "Card-paid orders" means orders whose CAPTURED attempt was card
--           (§5.3a), not orders that merely tried card.
--           Order-level money broken down by a product dimension is attributed
--           ENTIRELY to the order's handset (§1.7a): the whole order value sits
--           against that handset's model, and the accessory lines contribute
--           nothing to the split.
-- excludes: test transactions (§1.1); pending and failed refunds; duplicate captures
with fx as (
    select c.rate_date,
           c.currency,
           cast(c.usd_per_unit / r.usd_per_unit as decimal(38,12)) as to_reporting
    from fx_rates c
    join fx_rates r on r.rate_date = c.rate_date and r.currency = 'USD'
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
      and a.method = 'card'
      and s.country_code = 'AE'
),
handset as (
    select i.order_id, min(p.model_name) as model_name
    from order_items i
    join products p on p.sku = i.sku
    where not p.is_accessory
    group by i.order_id
),
captured as (
    select h.model_name,
           sum(c.amount_minor * fx.to_reporting) as amount
    from captures c
    join fx on fx.currency = c.currency and fx.rate_date = c.business_date
    join handset h on h.order_id = c.order_id
    where c.capture_rank = 1
      and c.business_date between date '2026-08-01' and date '2026-08-31'
    group by h.model_name
),
refunded as (
    select h.model_name,
           sum(rf.amount_minor * fx.to_reporting) as amount
    from refunds rf
    join captures c on c.order_id = rf.order_id and c.capture_rank = 1
    join fx on fx.currency = rf.currency and fx.rate_date = rf.business_date
    join handset h on h.order_id = rf.order_id
    where rf.status = 'processed'
      and rf.business_date between date '2026-08-01' and date '2026-08-31'
    group by h.model_name
)
select captured.model_name as key,
       cast(coalesce(refunded.amount, 0) / captured.amount as decimal(38,12)) as value
from captured
left join refunded on refunded.model_name = captured.model_name
order by value desc, key asc
limit 10
