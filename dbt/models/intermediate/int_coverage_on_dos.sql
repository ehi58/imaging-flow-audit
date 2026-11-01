-- For every claim line: the coverage of the billed payer in force on the date
-- of service (if any) and the expected primary payer on that date.
with lines as (select * from {{ ref('stg_claim_lines') }}),
cov as (select * from {{ ref('stg_coverage') }})
select
  l.claim_line_id, l.mrn, l.payer_id, l.member_id, l.date_of_service,
  (select max(c.member_id) from cov c where c.mrn = l.mrn and c.payer_id = l.payer_id and c.start_date <= l.date_of_service and l.date_of_service <= c.end_date) as covered_member_id,
  (select count(*) from cov c where c.mrn = l.mrn and c.payer_id = l.payer_id and c.start_date <= l.date_of_service and l.date_of_service <= c.end_date) as covering_periods,
  (select min(c.payer_id) from cov c where c.mrn = l.mrn and c.priority = 1 and c.start_date <= l.date_of_service and l.date_of_service <= c.end_date) as expected_primary_payer
from lines l
