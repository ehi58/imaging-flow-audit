-- E07: the claim went to a payer other than the primary in force on the date of service.
select claim_line_id as record_key, 'E07' as rule
from {{ ref('int_coverage_on_dos') }}
where expected_primary_payer is not null and payer_id <> expected_primary_payer
