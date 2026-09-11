-- qid:      EV-115
-- value:    money_minor
-- shape:    ranking
-- window:   july_2026          -> 2026-07-01 .. 2026-07-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   net revenue (§2.5), by acquiring bank
-- scope:    country IN
-- currency: INR (§1.4 rule 1 -- "in rupees")
-- top_k:    10
-- rule:     FLAG -- THE ROW DECLARES `kind: scalar` AND ALSO `top_k: 10`, AND THE
--           QUESTION SAYS "BY ACQUIRING BANK". A scalar net revenue "by acquiring bank" is
--           not a quantity. Two of the three signals -- the question text and top_k --
--           agree that this is a ranking, so the reference is a ranking, and the
--           inconsistency is reported rather than silently resolved. The question file is
--           frozen to this session. See the M3 report.
--           Net revenue is captured GMV minus refunds PROCESSED in the same window (§2.5).
--           ACQUIRING bank is Kestrel's bank, not the customer's issuing bank (§1.9).
--           The refund side is attributed to the acquiring bank of its order's capture, so
--           both sides describe the same bank.
-- excludes: test transactions (§1.1); pending and failed refunds; duplicate captures
with fx as (
    select c.rate_date,
           c.currency,
           cast(c.usd_per_unit / r.usd_per_unit as decimal(38,12)) as to_reporting
    from fx_rates c
    join fx_rates r on r.rate_date = c.rate_date and r.currency = 'INR'
),
captures as (
    select a.order_id, a.amount_minor, a.currency, a.business_date, a.acquiring_bank,
           row_number() over (
               partition by a.order_id, a.amount_minor
               order by a.attempt_no, a.attempt_id
           ) as capture_rank
    from payment_attempts a
    join orders o on o.order_id = a.order_id
    join showrooms s on s.showroom_id = o.showroom_id
    where a.status = 'captured'
      and not a.is_test
      and not o.is_test
      and s.country_code = 'IN'
      
),
captured as (
    select c.acquiring_bank, sum(c.amount_minor * fx.to_reporting) as amount
    from captures c join fx on fx.currency = c.currency and fx.rate_date = c.business_date
    where c.capture_rank = 1
      and c.business_date between date '2026-07-01' and date '2026-07-31'
    group by c.acquiring_bank
),
refunded as (
    select c.acquiring_bank, sum(rf.amount_minor * fx.to_reporting) as amount
    from refunds rf
    join captures c on c.order_id = rf.order_id and c.capture_rank = 1
    join fx on fx.currency = rf.currency and fx.rate_date = rf.business_date
    where rf.status = 'processed'
      and rf.business_date between date '2026-07-01' and date '2026-07-31'
    group by c.acquiring_bank
)
select captured.acquiring_bank as key,
       cast(round(captured.amount - coalesce(refunded.amount, 0)) as bigint) as value
from captured left join refunded on refunded.acquiring_bank = captured.acquiring_bank
order by value desc, key asc limit 10
