-- qid:      HO-031
-- value:    money_minor
-- shape:    ranking
-- window:   last_month         -> 2026-08-01 .. 2026-08-31   (GLOSSARY §1.6a, as_of 2026-09-10)
-- metric:   captured GMV (§2.3) by issuing bank, for instalment orders
-- scope:    country IN, orders paid by EMI
-- currency: INR (§1.4 rule 1 -- the asker named it)
-- top_k:    10
-- rule:     the value counted is the FULL ORDER VALUE, never the monthly instalment
--           (§4.9, §2.11): using the instalment where the order value belongs
--           understates revenue by the tenure, so a twelve-month order would look like
--           one twelfth of its size. The captured amount on the attempt IS the order
--           value, so nothing has to be multiplied back up.
--           "EMI orders" means orders whose CAPTURED attempt used EMI (§5.3a, §6.1) --
--           the paying method, not §1.9's "tried" rule.
--           A per-bank VALUE split attributes each amount to the attempt that actually
--           carried it (§1.9, "value and count metrics follow the money"), and the
--           method and the issuing bank are both on that same capturing attempt. These
--           breakdowns do partition the total and do sum to it, unlike per-bank success
--           rates.
--           Keyed on capture business date (§2.3). Captured money only (§4.2); the
--           duplicate side of a duplicate capture is counted once (§4.10).
--           Attempts carrying no issuing bank are not a bank and are dropped, not
--           bucketed under an empty key.
--           The scope is one country and one currency, so no conversion arises (§1.3).
-- excludes: test orders and test attempts (§1.1); duplicate captures; attempts with no
--           issuing bank
with captures as (
    select a.order_id, a.amount_minor, a.business_date, a.method, a.issuing_bank,
           row_number() over (
               partition by a.order_id, a.amount_minor
               order by a.attempt_no, a.attempt_id
           ) as capture_rank
    from payment_attempts a
    where a.status = 'captured'
      and not a.is_test
)
select c.issuing_bank as key,
       cast(sum(c.amount_minor) as bigint) as value
from captures c
join orders o on o.order_id = c.order_id
join showrooms s on s.showroom_id = o.showroom_id
where c.capture_rank = 1
  and not o.is_test
  and s.country_code = 'IN'
  and c.method = 'emi'
  and c.issuing_bank is not null
  and c.business_date between date '2026-08-01' and date '2026-08-31'
group by c.issuing_bank
order by value desc, key asc
limit 10
