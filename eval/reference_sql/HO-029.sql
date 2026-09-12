-- qid:      HO-029
-- value:    count
-- shape:    scalar
-- window:   yesterday          -> 2026-09-09 .. 2026-09-09   (GLOSSARY §1.7, as_of 2026-09-10)
-- metric:   units sold (§2.2), HANDSETS ONLY
-- scope:    all countries
-- currency: none (a count)
-- rule:     "Phones", "phone model", "handset" and "device" ALWAYS mean handsets only
--           and exclude accessories (§2.2, §5.2). "Units" is the opposite and counts
--           everything, so the phones-only figure is a filtered version of units sold
--           rather than a separate metric. Getting this backwards inflates the answer
--           by the whole accessory business.
--           Only PAID orders contribute; lines on abandoned or cancelled orders are
--           excluded (§2.2). Quantity is summed, so two of the same phone on one order
--           counts as two.
--           "Yesterday" means the SHOWROOM'S OWN LOCAL business date, one day before
--           the reporting date (§1.7, §4.5) -- not the 24 hours before midnight UTC,
--           which for Chennai would start at 5:30 a.m. local and pull in five and a
--           half hours of the wrong day. The question spans countries, so yesterday
--           resolves per showroom in its own timezone: every showroom's 9 September is
--           included even though they are different absolute moments (§1.7).
--           The reporting date is injected, never read from a clock (D2, §1.7).
-- excludes: test orders (§1.1); accessories; abandoned and cancelled orders
select cast(sum(i.qty) as bigint) as value
from order_items i
join orders o on o.order_id = i.order_id
join products p on p.sku = i.sku
where not o.is_test
  and o.status = 'paid'
  and not p.is_accessory
  and o.business_date = date '2026-09-09'
order by value
