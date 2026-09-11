-- qid:      EV-075
-- value:    count
-- shape:    ranking
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   units sold (§2.2), by colour
-- scope:    region IN-TN (Tamil Nadu)
-- currency: none
-- top_k:    8
-- rule:     colour is a governed product dimension (§1.7a).
--           Units counts LINES, so an accessory is its own unit and belongs to ITSELF, not
--           to the handset it was bought with (§2.2, §1.7a). This is the one place where a
--           product breakdown of units and of money describe different things, and the
--           difference is intended.
--           Accessories carry no colour in this schema, so they have no value for this
--           dimension and are out of the breakdown -- the same treatment a non-card
--           attempt gets in a card-network breakdown. The colour dimension is a handset
--           attribute (§1.7a).
--           Only PAID orders contribute (§2.2).
--           NOTE: top_k is 8 and only four colours exist, so the ranking is four rows.
-- excludes: test orders (§1.1); abandoned and cancelled orders; lines with no colour
select p.colour as key, sum(i.qty) as value
from order_items i
join orders o on o.order_id = i.order_id
join products p on p.sku = i.sku
join showrooms s on s.showroom_id = o.showroom_id
where not o.is_test and o.status = 'paid' and s.region_id = 'IN-TN'
  and p.colour <> ''
  and o.business_date between date '2026-08-01' and date '2026-08-31'
group by p.colour order by value desc, key asc limit 8
