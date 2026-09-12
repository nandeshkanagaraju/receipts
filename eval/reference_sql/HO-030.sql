-- qid:      HO-030
-- value:    count
-- shape:    ranking
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   units sold (§2.2), HANDSETS ONLY, by storage size
-- scope:    country GB
-- currency: none (a count)
-- top_k:    5
-- rule:     "Phones" means handsets only (§2.2, §5.2); accessories are excluded.
--           The storage size here is the LINE'S OWN product, not the order's handset.
--           §1.7a's rule that a product breakdown attributes the whole order value to
--           the handset governs order-level MONEY; it says explicitly that "units sold
--           is not affected", because units counts lines and an accessory belongs to
--           itself. With accessories already excluded the two readings coincide, and
--           the line-level reading is the one §2.2 defines.
--           Only PAID orders contribute (§2.2); quantity is summed, not lines counted.
--           Keyed on the order business date of the order the line belongs to (§2.2).
--           A storage size with no sales is an exact zero, not a missing row
--           (docs/M2_NOTES.md §5).
-- excludes: test orders (§1.1); accessories; abandoned and cancelled orders
with spine as (
    select distinct p.storage_gb
    from products p
    where not p.is_accessory
),
valued as (
    select p.storage_gb, sum(i.qty) as units
    from order_items i
    join orders o on o.order_id = i.order_id
    join showrooms s on s.showroom_id = o.showroom_id
    join products p on p.sku = i.sku
    where not o.is_test
      and o.status = 'paid'
      and not p.is_accessory
      and s.country_code = 'GB'
      and o.business_date between date '2026-08-01' and date '2026-08-31'
    group by p.storage_gb
)
select cast(sp.storage_gb as varchar) as key,
       cast(coalesce(v.units, 0) as bigint) as value
from spine sp
left join valued v on v.storage_gb = sp.storage_gb
order by value desc, key asc
limit 5
