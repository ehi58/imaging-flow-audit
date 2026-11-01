-- E12: one patient at the stop means R0070; more means R0075 with the count
-- modifier (UN 2, UP 3, UQ 4, UR 5, US 6+); a transport line on a day the
-- patient had no exam at that stop is a line for a trip that did not happen.
with transport as (select * from {{ ref('stg_claim_lines') }} where hcpcs in ('R0070', 'R0075')),
stops as (
  select trip_id, count(distinct mrn) as patients from {{ ref('stg_dispatch') }} group by trip_id
),
expected as (
  select t.*, s.patients,
    case when s.patients = 1 then 'R0070' else 'R0075' end as expected_hcpcs,
    case when s.patients = 1 then '' when s.patients = 2 then 'UN' when s.patients = 3 then 'UP'
         when s.patients = 4 then 'UQ' when s.patients = 5 then 'UR' else 'US' end as expected_modifier
  from transport t left join stops s on s.trip_id = t.trip_id
)
select claim_line_id as record_key, 'E12' as rule
from expected e
where e.patients is null
   or e.hcpcs <> e.expected_hcpcs
   or coalesce(e.modifiers, '') <> e.expected_modifier
   or not exists (
     select 1 from {{ ref('stg_dispatch') }} d where d.trip_id = e.trip_id and d.mrn = e.mrn and d.date = e.date_of_service
   )
