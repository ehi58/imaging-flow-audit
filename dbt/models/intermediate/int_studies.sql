-- One row per DICOM study, from the instances. The header accession is what
-- the modality wrote, which may differ from the order's (E01).
select
  study_uid,
  min(accession) as accession,
  min(patient_id) as patient_id,
  min(study_datetime) as study_datetime,
  cast(min(study_datetime) as date) as study_date,
  min(modality) as modality,
  min(body_part_examined) as body_part_examined,
  bool_and(body_part_tag_present) as body_part_tag_present,
  min(laterality) as laterality,
  min(image_laterality) as image_laterality,
  count(*) as instance_count
from {{ ref('stg_dicom_instances') }}
group by study_uid
