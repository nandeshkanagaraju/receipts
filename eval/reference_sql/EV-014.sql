-- qid:      EV-014
-- value:    count
-- shape:    compare
-- window:   last_week          -> 2026-08-31 .. 2026-09-06   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   units sold (§2.2)
-- scope:    country GB
-- currency: none
-- rule:     both windows are COMPLETE Monday-Sunday weeks and therefore equal length
--           (§1.6, §1.6a): 2026-08-31..2026-09-06 against 2026-08-24..2026-08-30.
--           Units counts every line, phones and accessories alike (§2.2), on PAID orders
--           only, keyed on the order's business date.
--           Both values are returned, keyed `current` and `comparison` (ADR-009).
-- excludes: test orders (§1.1); abandoned and cancelled orders
select case when o.business_date >= date '2026-08-31' then 'current' else 'comparison' end as key,
       sum(i.qty) as value
from order_items i
join orders o on o.order_id = i.order_id
join showrooms s on s.showroom_id = o.showroom_id
where not o.is_test and o.status = 'paid' and s.country_code = 'GB'
  and o.business_date between date '2026-08-24' and date '2026-09-06'
group by key order by key asc
