-- qid:      HO-035
-- value:    ratio
-- shape:    scalar
-- window:   fy2026_q3          -> 2025-10-01 .. 2025-12-31   (GLOSSARY §1.5)
-- metric:   refund rate (§2.7)
-- scope:    country IN
-- currency: none (a ratio has no currency, §2.7)
-- rule:     THE FISCAL YEAR IS NAMED FOR THE YEAR IT ENDS IN (§1.5). FY2026 runs
--           1 April 2025 to 31 March 2026, its quarters are Q1 April-June, Q2
--           July-September, Q3 October-December, Q4 January-March -- so fiscal Q3 of
--           FY2026 is October to December 2025. Calendar Q3 2026 would be July to
--           September 2026, a different window and a different number.
--           The question names the calendar explicitly ("fiscal Q3 of FY2026"), so it
--           is answered directly rather than clarified (§4.6, §6.2). An unqualified
--           "Q3" would have to be clarified.
--           Refund rate is VALUE-based, not count-based (§2.7, §6.1). Each side keys on
--           its own date: refunds on refund business date, captures on capture business
--           date (§2.7).
--           The scope is one country and one currency, so no conversion arises (§1.3).
-- excludes: test orders and test attempts (§1.1); pending and failed refunds (§2.4);
--           duplicate captures (§4.10)
with captures as (
    select a.order_id, a.amount_minor, a.business_date,
           row_number() over (
               partition by a.order_id, a.amount_minor
               order by a.attempt_no, a.attempt_id
           ) as capture_rank
    from payment_attempts a
    where a.status = 'captured'
      and not a.is_test
),
scoped_orders as (
    select o.order_id
    from orders o
    join showrooms s on s.showroom_id = o.showroom_id
    where not o.is_test
      and s.country_code = 'IN'
),
captured as (
    select sum(c.amount_minor) as gmv_minor
    from captures c
    join scoped_orders so on so.order_id = c.order_id
    where c.capture_rank = 1
      and c.business_date between date '2025-10-01' and date '2025-12-31'
),
refunded as (
    select sum(rf.amount_minor) as refund_minor
    from refunds rf
    join scoped_orders so on so.order_id = rf.order_id
    where rf.status = 'processed'
      and rf.business_date between date '2025-10-01' and date '2025-12-31'
)
select cast(coalesce((select refund_minor from refunded), 0) * 1.0
            / (select gmv_minor from captured) as decimal(38,12)) as value
order by value
