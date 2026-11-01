select
  claim_line_id, claim_id, nullif(accession, '') as accession, trip_id, mrn,
  try_cast(date_of_service as date) as date_of_service, place_of_service, hcpcs,
  modifiers, try_cast(units as integer) as units, ordering_npi, rendering_npi, billing_npi, payer_id, member_id,
  try_cast(charge as double) as charge
from {{ source('warehouse', 'claim_lines') }}
