-- qid:      HO-014
-- value:    count
-- shape:    scalar
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   accessory-bearing order count -- NOT a glossary metric; the row's
--           `interpretation` governs (ADR-009)
-- scope:    country GB
-- currency: none (a count)
-- rule:     the row carries an `interpretation` because the glossary defines the
--           accessory attach RATE (§2.12) but not a bare count of its numerator, and
--           that sentence governs.
--           Distinct PAID orders having at least one accessory line. Abandoned and
--           cancelled orders are excluded, exactly as §2.12 excludes them: they
--           contributed nothing to attach.
--           This is §2.12's numerator on its own. It is a count of ORDERS, not of
--           accessory lines or accessory units -- an order with three accessories
--           counts once.
--           Keyed on ORDER business date (§2.12).
--           "Accessory" is the product flag, never a guess from the name (§1.1's
--           posture on flags over name matching).
-- excludes: test orders (§1.1); abandoned and cancelled orders
select count(distinct o.order_id) as value
from orders o
join showrooms s on s.showroom_id = o.showroom_id
join order_items i on i.order_id = o.order_id
join products p on p.sku = i.sku
where not o.is_test
  and o.status = 'paid'
  and s.country_code = 'GB'
  and p.is_accessory
  and o.business_date between date '2026-08-01' and date '2026-08-31'
order by value
