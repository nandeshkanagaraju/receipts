-- qid:      HO-028
-- value:    count
-- shape:    scalar
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   count of PAID orders (§2.1, §2.6) -- not orders count
-- scope:    region IN-TN (Tamil Nadu)
-- currency: none (a count)
-- rule:     "How many orders did we get paid for" is the count of `paid` orders and is
--           explicitly NOT orders count (§5.2, §2.1). Orders count takes all three
--           statuses -- paid, abandoned and cancelled -- so it is the larger number;
--           this one is the denominator of average order value (§2.6).
--           Keyed on ORDER business date, the showroom's own local date (§1.2, §4.5).
--           Test orders are excluded by the flag, always, and never by matching on
--           names, amounts or customer details (§1.1, §4.8). They live in the same
--           table as real ones and are a small share of rows, which is exactly why they
--           survive -- they move a number by a few percent, which reads as noise.
-- excludes: test orders (§1.1, §4.8); abandoned and cancelled orders
select count(*) as value
from orders o
join showrooms s on s.showroom_id = o.showroom_id
where not o.is_test
  and o.status = 'paid'
  and s.region_id = 'IN-TN'
  and o.business_date between date '2026-08-01' and date '2026-08-31'
order by value
