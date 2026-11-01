-- E02: for a sided order, ImageLaterality (fallback Laterality) must equal the
-- ordered side. Chest and other unpaired parts have no side and are not judged.
select study_uid as record_key, 'E02' as rule
from {{ ref('int_exam_spine') }}
where study_uid is not null
  and ordered_laterality in ('L', 'R')
  and coalesce(nullif(image_laterality, ''), nullif(study_laterality, '')) is distinct from ordered_laterality
