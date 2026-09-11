-- qid:      HO-043
-- value:    ratio
-- shape:    scalar
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   EMI share (§2.11)
-- scope:    country GB
-- currency: none (a ratio, §2.11)
-- rule:     EMI IS OFFERED ONLY IN INDIA AND MALAYSIA, so an EMI share for the UK is
--           LEGITIMATELY ZERO rather than missing (§2.11). This is the question that
--           turns on the rule in docs/M2_NOTES.md §5: the answer is A ROW CONTAINING
--           ZERO, never zero rows. An empty result and a result of zero are different
--           claims -- the first says the question could not be answered, the second says
--           no instalment money was captured -- and the scorer cannot tell them apart
--           afterwards.
--           So the numerator is a conditional sum over the SAME rows as the denominator,
--           not a filtered subquery that would return no rows at all.
--           Numerator: captured GMV from orders paid by EMI. Denominator: total captured
--           GMV (§2.11). The denominator is non-zero, so the ratio is defined.
--           The value counted is the FULL ORDER VALUE, never the monthly instalment
--           (§4.9).
--           Keyed on capture business date (§2.11).
--           The scope is one country and one currency, so no conversion arises (§1.3).
-- excludes: test orders and test attempts (§1.1); duplicate captures (§4.10)
with captures as (
    select a.order_id, a.amount_minor, a.business_date, a.method,
           row_number() over (
               partition by a.order_id, a.amount_minor
               order by a.attempt_no, a.attempt_id
           ) as capture_rank
    from payment_attempts a
    where a.status = 'captured'
      and not a.is_test
)
select cast(sum(case when c.method = 'emi' then c.amount_minor else 0 end) * 1.0
            / sum(c.amount_minor) as decimal(38,12)) as value
from captures c
join orders o on o.order_id = c.order_id
join showrooms s on s.showroom_id = o.showroom_id
where c.capture_rank = 1
  and not o.is_test
  and s.country_code = 'GB'
  and c.business_date between date '2026-08-01' and date '2026-08-31'
order by value
