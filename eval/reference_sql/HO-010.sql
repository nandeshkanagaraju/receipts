-- qid:      HO-010
-- value:    ratio
-- shape:    scalar
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (on ATTEMPT business date)
-- metric:   capture rate of authorised payments -- NOT a glossary metric; the row's
--           `interpretation` governs (ADR-009)
-- scope:    country GB
-- currency: none (a ratio)
-- rule:     the row carries an `interpretation` because the glossary defines no ratio
--           between authorisation and capture, and that sentence governs the
--           numerator, the denominator, the date key and the exclusions.
--           Numerator: attempts that reached `captured`.
--           Denominator: attempts that reached `authorized` OR `captured`. Failed
--           attempts are in neither -- they were never authorised.
--           §4.2: an authorisation reserves the customer's funds, a capture takes
--           them, and only the capture is revenue. Since ADR-014 roughly 2% of card
--           attempts end `authorized` -- funds reserved, the hold expired or was
--           voided, never captured -- so this denominator is materially larger than
--           the numerator and the question has a real answer.
--           No breakdown by bank, network or reason: an `authorized` row inherits the
--           failure distribution wholesale, so such a breakdown would report a
--           planted anomaly as an authorisation pattern (ADR-014, LIMITATIONS.md).
--           Keyed on the attempt's own business date (§1.2).
-- excludes: test attempts and test orders (§1.1)
select cast(sum(case when a.status = 'captured' then 1 else 0 end) * 1.0 / count(*)
            as decimal(38,12)) as value
from payment_attempts a
join orders o on o.order_id = a.order_id
join showrooms s on s.showroom_id = o.showroom_id
where not a.is_test
  and not o.is_test
  and s.country_code = 'GB'
  and a.status in ('authorized', 'captured')
  and a.business_date between date '2026-08-01' and date '2026-08-31'
order by value
