select
  accession, placer_order_number, filler_order_number, mrn, control, order_status,
  try_cast(order_datetime as timestamp) as order_datetime,
  try_cast(scheduled_datetime as timestamp) as scheduled_datetime,
  cpt, description, nullif(laterality, '') as laterality, ordering_npi, reason, study_uid, modality
from {{ source('warehouse', 'orders') }}
