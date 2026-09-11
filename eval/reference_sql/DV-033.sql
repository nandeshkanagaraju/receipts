-- qid:      DV-033
-- value:    count
-- shape:    scalar
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   NOT a Kestrel metric -- distinct issuing bank count, per the row's `interpretation`
-- scope:    country GB
-- currency: none
-- rule:     interpretation: "number of distinct non-null issuing_bank values on
--           non-test payment attempts at UK showrooms in the window, keyed on
--           attempt business date."
--           Issuing bank and acquiring bank are DIFFERENT dimensions (§1.9) and
--           this counts the issuing side -- the customer's bank, not Kestrel's.
--           NULL is not a bank: non-card methods carry no issuing bank and are
--           not counted as one more.
-- excludes: test attempts (§1.1)
select count(distinct a.issuing_bank) as value
from payment_attempts a
join orders o on o.order_id = a.order_id
join showrooms s on s.showroom_id = o.showroom_id
where not a.is_test
  and a.issuing_bank is not null
  and s.country_code = 'GB'
  and a.business_date between date '2026-08-01' and date '2026-08-31'
order by value
