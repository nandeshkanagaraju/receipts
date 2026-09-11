-- qid:      HO-B04
-- value:    money_minor
-- shape:    ranking
-- window:   last_30_days       -> 2026-08-11 .. 2026-09-09   (read as §1.6a reads "last 7 days")
-- metric:   captured GMV (§2.3) by showroom
-- scope:    region IN-TN (Tamil Nadu)
-- currency: INR (§1.4 rule 2 -- rm_tamil_nadu reports in INR)
-- top_k:    5
-- rule:     the row carries an `interpretation` because "the last 30 days" is not a
--           window the glossary names, and that sentence governs. It is read exactly as
--           §1.6a reads "the last 7 days": the N days ENDING YESTERDAY, with the
--           reporting day excluded because it is not over and a partial day would
--           understate its own figure.
--           "Sales value" is captured GMV (§6.1: "sales" unqualified is money, not
--           units), captured and not merely authorised (§4.2), and not settled money
--           (§5.1) -- three different numbers.
--           The duplicate side of a duplicate capture is counted once (§4.10).
--           Keyed on capture business date (§2.3).
--           The scope is one region and one currency, so no conversion arises (§1.3).
-- excludes: test orders and test attempts (§1.1); duplicate captures
with captures as (
    select a.order_id, a.amount_minor, a.currency, a.business_date,
           row_number() over (
               partition by a.order_id, a.amount_minor
               order by a.attempt_no, a.attempt_id
           ) as capture_rank
    from payment_attempts a
    where a.status = 'captured'
      and not a.is_test
)
select s.name as key,
       cast(sum(c.amount_minor) as bigint) as value
from captures c
join orders o on o.order_id = c.order_id
join showrooms s on s.showroom_id = o.showroom_id
where c.capture_rank = 1
  and not o.is_test
  and s.region_id = 'IN-TN'
  and c.business_date between date '2026-08-11' and date '2026-09-09'
group by s.name
order by value desc, key asc
limit 5
