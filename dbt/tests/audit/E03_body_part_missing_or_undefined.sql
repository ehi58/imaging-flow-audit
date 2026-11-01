-- E03: BodyPartExamined present, non-empty and in the defined-terms vocabulary (case-sensitive).
select s.study_uid as record_key, 'E03' as rule
from {{ ref('int_studies') }} s
where not s.body_part_tag_present
   or coalesce(s.body_part_examined, '') = ''
   or s.body_part_examined not in (select code from {{ ref('stg_vocab') }} where kind = 'body_part')
