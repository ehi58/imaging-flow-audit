select
  mrn, payer_id, payer_name, plan_type, try_cast(priority as integer) as priority, member_id,
  try_cast(start_date as date) as start_date, try_cast(end_date as date) as end_date
from {{ source('warehouse', 'coverage') }}
