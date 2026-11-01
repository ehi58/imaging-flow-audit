select trip_id, try_cast(date as date) as date, facility_id, technologist_npi, accession, mrn
from {{ source('warehouse', 'dispatch') }}
