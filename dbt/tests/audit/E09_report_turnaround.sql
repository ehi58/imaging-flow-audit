-- E09: no final report, a report before the exam, or a report past the SLA.
select accession as record_key, 'E09' as rule
from {{ ref('int_exam_spine') }}
where report_datetime is null
   or report_datetime < exam_datetime
   or report_datetime > exam_datetime + interval '{{ var("sla_hours") }}' hour
