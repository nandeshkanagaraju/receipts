-- qid:      HO-009
-- value:    ratio
-- shape:    ranking
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   EMI share (§2.11) by acquiring bank
-- scope:    country IN
-- currency: none (a ratio, §2.11)
-- top_k:    10
-- rule:     EMI share is a share of captured VALUE, not a count of orders (§2.11).
--           The value counted is the FULL ORDER VALUE, never the monthly instalment
--           (§4.9, §2.11): using the instalment where the order value belongs
--           understates revenue by the tenure, so a twelve-month order would look
--           like one twelfth of its size.
--           Read per bank: the numerator is that bank's EMI captures, the denominator
--           that bank's total captures. The shares therefore describe each bank and do
--           not average to a national figure.
--           The bank and the method both live on the capturing attempt, so the money
--           is already attached to one attempt and no order-level attribution rule is
--           needed (§1.9, "value and count metrics follow the money").
--           Keyed on capture business date (§2.11).
--           A bank with no captures in the window has no denominator and therefore no
--           cell -- a rate over nothing is not zero.
--           The scope is one country and one currency, so no conversion arises (§1.3).
-- excludes: test orders and test attempts (§1.1); duplicate captures (§4.10)
with captures as (
    select a.order_id, a.amount_minor, a.business_date, a.method, a.acquiring_bank,
           row_number() over (
               partition by a.order_id, a.amount_minor
               order by a.attempt_no, a.attempt_id
           ) as capture_rank
    from payment_attempts a
    where a.status = 'captured'
      and not a.is_test
),
scoped as (
    select c.acquiring_bank, c.method, c.amount_minor
    from captures c
    join orders o on o.order_id = c.order_id
    join showrooms s on s.showroom_id = o.showroom_id
    where c.capture_rank = 1
      and not o.is_test
      and s.country_code = 'IN'
      and c.business_date between date '2026-08-01' and date '2026-08-31'
)
select acquiring_bank as key,
       cast(sum(case when method = 'emi' then amount_minor else 0 end) * 1.0
            / sum(amount_minor) as decimal(38,12)) as value
from scoped
group by acquiring_bank
having sum(amount_minor) > 0
order by value desc, key asc
limit 10
