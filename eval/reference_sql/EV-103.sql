-- qid:      EV-103
-- value:    count
-- shape:    list
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   TWO metrics -- captured GMV (§2.3) and units sold (§2.2), by phone model
-- scope:    region IN-TN (Tamil Nadu)
-- currency: INR (§1.4 rule 1 -- "in rupees"); applies to the money rows only
-- top_k:    5
-- rule:     the question asks TWO things at once -- which model brought in the most
--           MONEY and which sold the most UNITS -- and §1.7a says plainly that these are
--           different questions with different answers.
--           Money: attributed ENTIRELY to the order's handset (§1.7a). Units: counts
--           LINES, so an accessory is its own unit and belongs to itself. A showroom or
--           model with a strong accessory business ranks differently on the two.
--           So the reference carries both, keyed `money|<model>` and `units|<model>`, and
--           an answer that gives only one has answered half the question.
--           SHAPE IS `list`, NOT `ranking`: the file holds TWO rankings concatenated, and
--           a single positional order over the union would be meaningless. The top-5
--           membership of each is what the question asks for, so the rows are compared
--           as a set (docs/M2_NOTES.md §5) and the `money|`/`units|` prefixes keep the
--           two apart.
--           MIXED VALUE KINDS: the money rows are INR minor units and the unit rows are
--           counts. Declared `count` because the shape cannot declare two; the `money|`
--           prefix is what distinguishes them. See the M3 report.
-- excludes: test transactions (§1.1); abandoned and cancelled orders for units; duplicate captures for money
with fx as (
    select c.rate_date,
           c.currency,
           cast(c.usd_per_unit / r.usd_per_unit as decimal(38,12)) as to_reporting
    from fx_rates c
    join fx_rates r on r.rate_date = c.rate_date and r.currency = 'INR'
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
      and s.region_id = 'IN-TN'
      and a.business_date between date '2026-08-01' and date '2026-08-31'
),
handset as (
    select i.order_id, min(p.model_name) as model_name
    from order_items i join products p on p.sku = i.sku
    where not p.is_accessory group by i.order_id
),
money as (
    select 'money|' || h.model_name as key,
           cast(round(sum(c.amount_minor * fx.to_reporting)) as bigint) as value
    from captures c
    join fx on fx.currency = c.currency and fx.rate_date = c.business_date
    join handset h on h.order_id = c.order_id
    where c.capture_rank = 1 group by h.model_name
    order by value desc, key asc limit 5
),
units as (
    select 'units|' || p.model_name as key, sum(i.qty) as value
    from order_items i
    join orders o on o.order_id = i.order_id
    join products p on p.sku = i.sku
    join showrooms s on s.showroom_id = o.showroom_id
    where not o.is_test and o.status = 'paid' and not p.is_accessory
      and s.region_id = 'IN-TN'
      and o.business_date between date '2026-08-01' and date '2026-08-31'
    group by p.model_name order by value desc, key asc limit 5
)
select key, value from (select * from money union all select * from units)
order by key asc
