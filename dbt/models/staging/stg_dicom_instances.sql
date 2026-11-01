select
  study_folder, accession, patient_id, patient_name, birth_date, sex, study_uid, series_uid, sop_uid,
  try_cast(study_datetime as timestamp) as study_datetime,
  body_part_examined, body_part_tag_present = '1' as body_part_tag_present,
  laterality, image_laterality, view_position, modality, referring_physician
from {{ source('warehouse', 'dicom_instances') }}
