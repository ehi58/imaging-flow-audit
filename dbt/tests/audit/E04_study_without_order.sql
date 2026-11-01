-- E04: a study with no order on its accession AND no order for the same
-- patient, date and modality left unmatched (that case is E01's).
with studies as (select * from {{ ref('int_studies') }}),
orders as (select * from {{ ref('stg_orders') }} where control = 'NW'),
unmatched_orders as (
  select o.* from orders o where not exists (select 1 from studies s where s.accession = o.accession)
)
select s.study_uid as record_key, 'E04' as rule
from studies s
where not exists (select 1 from orders o where o.accession = s.accession)
  and not exists (
    select 1 from unmatched_orders u
    where u.mrn = s.patient_id and cast(u.scheduled_datetime as date) = s.study_date and u.modality = s.modality
  )
