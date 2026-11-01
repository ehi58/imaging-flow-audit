select
  placer_order_number, filler_order_number, mrn, cpt,
  try_cast(exam_datetime as timestamp) as exam_datetime,
  try_cast(report_datetime as timestamp) as report_datetime,
  status, reader_npi, text
from {{ source('warehouse', 'reports') }}
