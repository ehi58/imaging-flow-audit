-- E11: the instance count of the study must equal the view count the billed CPT implies.
select e.tc_claim_line_id as record_key, 'E11' as rule
from {{ ref('int_exam_spine') }} e
join {{ ref('stg_vocab') }} v on v.kind = 'procedure' and v.code = e.billed_hcpcs
where e.study_uid is not null and e.tc_claim_line_id is not null
  and e.instance_count <> v.views
