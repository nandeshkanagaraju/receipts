-- qid:      DV-031
-- value:    ratio
-- shape:    ranking
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   accessory attach rate (§2.12), by showroom
-- scope:    city Chennai
-- currency: none
-- top_k:    5
-- rule:     numerator: paid orders containing at least one PHONE line AND at
--           least one ACCESSORY line. Denominator: paid orders containing at
--           least one phone line (§2.12). Accessory-only orders are in neither
--           -- nothing was attached to anything -- though in Kestrel's data
--           every order carries exactly one handset (§1.7a), so the case does
--           not arise.
--           This is a count of ORDERS, not a split of money, so the §1.7a
--           handset-attribution rule does not apply to it (§1.7a, §2.12).
--           Keyed on ORDER business date (§2.12).
-- excludes: test orders (§1.1); abandoned and cancelled orders (§2.12)
with lines as (
    select o.order_id,
           s.name as showroom,
           max(case when not p.is_accessory then 1 else 0 end) as has_phone,
           max(case when p.is_accessory then 1 else 0 end) as has_accessory
    from orders o
    join order_items i on i.order_id = o.order_id
    join products p on p.sku = i.sku
    join showrooms s on s.showroom_id = o.showroom_id
    join cities ci on ci.city_id = s.city_id
    where not o.is_test
      and o.status = 'paid'
      and ci.name = 'Chennai'
      and o.business_date between date '2026-08-01' and date '2026-08-31'
    group by o.order_id, s.name
)
select showroom as key,
       cast(sum(has_accessory) * 1.0 / count(*) as decimal(38,12)) as value
from lines
where has_phone = 1
group by showroom
order by value desc, key asc
limit 5
