-- qid:      EV-122
-- value:    money_minor
-- shape:    ranking
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   average order value (§2.6) for card-paid orders, by card network
-- scope:    country SG, card-paid orders only
-- currency: SGD (§1.4 rule 1 -- "in Singapore dollars")
-- top_k:    5
-- rule:     "card-paid orders" means orders whose CAPTURED attempt was card (§5.3a) --
--           the method the money came in on. This is NOT the "tried" rule of §1.9, which
--           governs success rates only: here the question filters a set of orders and
--           splits their value, so the order belongs to the network that paid.
--           AOV is captured GMV over distinct PAID orders, both keyed on capture business
--           date (§2.6).
-- excludes: test transactions (§1.1); duplicate captures
with fx as (
    select c.rate_date,
           c.currency,
           cast(c.usd_per_unit / r.usd_per_unit as decimal(38,12)) as to_reporting
    from fx_rates c
    join fx_rates r on r.rate_date = c.rate_date and r.currency = 'SGD'
),
captures as (
    select a.order_id, a.amount_minor, a.currency, a.business_date, a.card_network,
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
      and s.country_code = 'SG' and a.method = 'card' and a.card_network is not null
      and a.business_date between date '2026-08-01' and date '2026-08-31'
)
select c.card_network as key,
       cast(round(
           sum(c.amount_minor * fx.to_reporting) / count(distinct c.order_id)
       ) as bigint) as value
from captures c join fx on fx.currency = c.currency and fx.rate_date = c.business_date
where c.capture_rank = 1 group by c.card_network order by value desc, key asc limit 5
