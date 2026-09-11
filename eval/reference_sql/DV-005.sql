-- qid:      DV-005
-- value:    days
-- shape:    scalar
-- window:   august_2026        -> 2026-08-01 .. 2026-08-31   (named month, as_of 2026-09-10)
-- metric:   settlement lag (§2.13)
-- scope:    all countries
-- currency: none
-- rule:     the window is keyed on SETTLEMENT date, not capture date (§2.13,
--           §4.7): "lag in August" means payments SETTLED in August. Captures
--           not yet settled have no lag to measure and are excluded from the
--           average; they are reported separately as unsettled amount (§2.14).
-- capability: finance (§2.13)
-- excludes: test attempts (§1.1)
select cast(sum(s.settled_on - a.business_date) * 1.0 / count(*) as decimal(38,12)) as value
from settlements s
join settlement_items si on si.settlement_id = s.settlement_id
join payment_attempts a on a.attempt_id = si.attempt_id
where not a.is_test
  and a.status = 'captured'
  and s.settled_on between date '2026-08-01' and date '2026-08-31'
order by value
