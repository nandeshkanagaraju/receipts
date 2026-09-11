-- qid:      DV-049
-- value:    count
-- shape:    scalar
-- window:   last_week          -> 2026-08-31 .. 2026-09-06   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   NOT a Kestrel metric -- failed card attempt count, per the row's `interpretation`
-- scope:    country GB, card attempts only
-- currency: none
-- rule:     interpretation: "number of non-test payment attempts with method
--           'card' and status 'failed' at UK showrooms in the window, keyed on
--           attempt business date. A count, not failure_rate_by_reason (§2.10),
--           whose denominator is all attempts."
--           A plain COUNT of failures is legitimate but undefined in the
--           glossary (§2.10): it is answerable from the tables without being a
--           Kestrel metric, which is why this row carries an interpretation.
-- excludes: test attempts (§1.1)
select count(*) as value
from payment_attempts a
join orders o on o.order_id = a.order_id
join showrooms s on s.showroom_id = o.showroom_id
where not a.is_test
  and a.method = 'card'
  and a.status = 'failed'
  and s.country_code = 'GB'
  and a.business_date between date '2026-08-31' and date '2026-09-06'
order by value
