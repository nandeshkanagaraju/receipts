-- qid:      EV-065
-- value:    count
-- shape:    compare
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   units sold (§2.2), by country
-- scope:    all countries
-- currency: none
-- top_k:    6
-- rule:     equal-length calendar months (§1.6a): August 2026 against August 2025.
--           Units counts every line, accessories included, on PAID orders only (§2.2).
--           Keys are `<country>|current` and `<country>|comparison` so both periods must
--           be present per country (ADR-009).
-- excludes: test orders (§1.1); abandoned and cancelled orders
select s.country_code || '|' ||
       case when o.business_date >= date '2026-01-01' then 'current' else 'comparison' end as key,
       sum(i.qty) as value
from order_items i
join orders o on o.order_id = i.order_id
join showrooms s on s.showroom_id = o.showroom_id
where not o.is_test and o.status = 'paid'
  and (o.business_date between date '2026-08-01' and date '2026-08-31'
    or o.business_date between date '2025-08-01' and date '2025-08-31')
group by key order by key asc
