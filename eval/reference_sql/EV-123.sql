-- qid:      EV-123
-- value:    count
-- shape:    scalar
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   NOT a Kestrel metric -- abandoned order count, per the row's `interpretation`
-- scope:    country GB
-- currency: none
-- rule:     interpretation: "non-test orders at UK showrooms in the window with status
--           'abandoned', keyed on order business date."
--           Orders count (§2.1) includes ALL THREE statuses -- paid, abandoned and
--           cancelled -- so a status-filtered count is not separately defined. Abandoned
--           orders are real business events and are counted in orders_count; nothing is
--           excluded by default except test transactions (§1.1).
-- excludes: test orders (§1.1)
select count(*) as value
from orders o
join showrooms s on s.showroom_id = o.showroom_id
where not o.is_test and o.status = 'abandoned' and s.country_code = 'GB'
  and o.business_date between date '2026-08-01' and date '2026-08-31'
order by value
