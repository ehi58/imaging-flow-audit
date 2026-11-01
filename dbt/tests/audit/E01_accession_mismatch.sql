-- E01: a study whose header accession finds no order, or an order for another
-- patient, WHILE an order for the same patient, date and modality is left
-- without a study of its own. That makes it a mismatch, not an orphan (E04).
with studies as (select * from {{ ref('int_studies') }}),
orders as (select * from {{ ref('stg_orders') }} where control = 'NW'),
matched as (
  select s.study_uid, s.accession, s.patient_id, s.study_date, s.modality, o.mrn as order_mrn
  from studies s left join orders o on o.accession = s.accession
),
unmatched_orders as (
  select o.* from orders o
  where not exists (select 1 from studies s where s.accession = o.accession)
)
select m.study_uid as record_key, 'E01' as rule
from matched m
where (m.order_mrn is null or m.order_mrn <> m.patient_id)
  and exists (
    select 1 from unmatched_orders u
    where u.mrn = m.patient_id and cast(u.scheduled_datetime as date) = m.study_date and u.modality = m.modality
  )
