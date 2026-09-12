-- qid:      HO-B16
-- value:    money_minor
-- shape:    scalar
-- window:   this_month_to_date -> 2026-09-01 .. 2026-09-09   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   average order value (§2.6)
-- scope:    city London
-- currency: GBP (§1.4 rule 2 -- store_ops_uk reports in GBP)
-- rule:     average order value is captured GMV divided by the number of orders that
--           PRODUCED it (§2.6). The denominator is distinct PAID orders -- orders with at
--           least one captured payment. Abandoned and cancelled orders are NOT in the
--           denominator: they contributed nothing to the numerator, and including them
--           would understate the average.
--           BOTH sides key on CAPTURE business date (§2.6), so the two describe the same
--           set of orders. Keying the denominator on order date instead would mix two
--           populations.
--           For orders paid by instalments the order value is the FULL order value,
--           never the monthly instalment (§2.6's note, §4.9).
--           "This month" is month-to-date and ends YESTERDAY (§1.6a, §5.4).
--           The duplicate side of a duplicate capture is counted once (§4.10), so a
--           double charge does not inflate the average.
--           The scope is one city and one currency, so no conversion arises (§1.3).
-- excludes: test orders and test attempts (§1.1); duplicate captures
with captures as (
    select a.order_id, a.attempt_id, a.amount_minor, a.currency, a.business_date,
           a.method, a.acquiring_bank,
           row_number() over (
               partition by a.order_id, a.amount_minor
               order by a.attempt_no, a.attempt_id
           ) as capture_rank
    from payment_attempts a
    where a.status = 'captured'
      and not a.is_test
)
select cast(round(sum(c.amount_minor) * 1.0 / count(distinct c.order_id)) as bigint) as value
from captures c
join orders o on o.order_id = c.order_id
join showrooms s on s.showroom_id = o.showroom_id
join cities ci on ci.city_id = s.city_id
where c.capture_rank = 1
  and not o.is_test
  and ci.name = 'London'
  and c.business_date between date '2026-09-01' and date '2026-09-09'
order by value
