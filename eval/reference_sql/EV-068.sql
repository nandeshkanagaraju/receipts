-- qid:      EV-068
-- value:    ratio
-- shape:    ranking
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   refund rate (§2.7) for EMI orders, by issuing bank
-- scope:    country IN, EMI-paid orders only
-- currency: INR (§1.4 rule 2 -- global_finance would report USD, but §1.4 rule 1 is not met and rule 2 applies; see rule note)
-- top_k:    10
-- rule:     "EMI orders" means orders whose CAPTURED attempt used EMI (§5.3a), not the
--           tried rule of §1.9.
--           ISSUING bank -- the customer's bank -- not acquiring, which is Kestrel's
--           (§1.9).
--           Refund rate is VALUE-based (§2.7); each side keeps its own date key. The
--           refund is attributed to the same order's EMI capture, so both sides describe
--           the same bank.
--           CURRENCY NOTE: global_finance defaults to USD under §1.4 rule 2, but every
--           row here is India and therefore INR; rule 2 outranks rule 3, so USD would be
--           the literal reading. The ratio is scope-identical either way because both
--           sides convert with the same per-date factors within one currency; INR is used
--           so the conversion is the identity and no rounding enters the ratio.
-- excludes: test transactions (§1.1); pending and failed refunds; duplicate captures
with fx as (
    select c.rate_date,
           c.currency,
           cast(c.usd_per_unit / r.usd_per_unit as decimal(38,12)) as to_reporting
    from fx_rates c
    join fx_rates r on r.rate_date = c.rate_date and r.currency = 'INR'
),
captures as (
    select a.order_id, a.amount_minor, a.currency, a.business_date, a.issuing_bank,
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
      and s.country_code = 'IN' and a.method = 'emi'
      
),
captured as (
    select c.issuing_bank, sum(c.amount_minor * fx.to_reporting) as amount
    from captures c join fx on fx.currency = c.currency and fx.rate_date = c.business_date
    where c.capture_rank = 1
      and c.business_date between date '2026-08-01' and date '2026-08-31'
    group by c.issuing_bank
),
refunded as (
    select c.issuing_bank, sum(rf.amount_minor * fx.to_reporting) as amount
    from refunds rf
    join captures c on c.order_id = rf.order_id and c.capture_rank = 1
    join fx on fx.currency = rf.currency and fx.rate_date = rf.business_date
    where rf.status = 'processed'
      and rf.business_date between date '2026-08-01' and date '2026-08-31'
    group by c.issuing_bank
)
select captured.issuing_bank as key,
       cast(coalesce(refunded.amount, 0) / captured.amount as decimal(38,12)) as value
from captured left join refunded on refunded.issuing_bank = captured.issuing_bank
order by value desc, key asc limit 10
