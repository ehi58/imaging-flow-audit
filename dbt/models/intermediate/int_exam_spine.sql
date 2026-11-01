-- Order <-> study (on accession) <-> report (on placer order) <-> technical-component claim line (on accession).
with orders as (select * from {{ ref('stg_orders') }} where control = 'NW'),
studies as (select * from {{ ref('int_studies') }}),
reports as (select * from {{ ref('stg_reports') }}),
tc as (
  select * from {{ ref('stg_claim_lines') }}
  where accession is not null and hcpcs <> 'Q0092'
)
select
  o.accession, o.placer_order_number, o.mrn, o.cpt as ordered_cpt, o.laterality as ordered_laterality,
  o.ordering_npi, o.scheduled_datetime, cast(o.scheduled_datetime as date) as exam_date,
  s.study_uid, s.accession as study_accession, s.instance_count, s.body_part_examined, s.laterality as study_laterality, s.image_laterality,
  r.exam_datetime, r.report_datetime, r.status as report_status,
  tc.claim_line_id as tc_claim_line_id, tc.hcpcs as billed_hcpcs, tc.payer_id, tc.member_id, tc.date_of_service
from orders o
left join studies s on s.accession = o.accession
left join reports r on r.placer_order_number = o.placer_order_number
left join tc on tc.accession = o.accession
