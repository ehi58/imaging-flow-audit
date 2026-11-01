-- E06: the billed payer had no coverage period in force on the date of service.
select claim_line_id as record_key, 'E06' as rule
from {{ ref('int_coverage_on_dos') }}
where payer_id <> 'SELF' and covering_periods = 0
