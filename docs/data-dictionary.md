# Data dictionary

Every table the flow writes, the key that joins it to the next hop, and where
the audit reads it from. All values are synthetic. Dates are ISO 8601; HL7 and
DICOM carry their own formats and the extract step normalises them.

## Vocabularies (`data/vocab/`, committed)

| file | columns | note |
|---|---|---|
| `payers.csv` | `payer_id`, `name`, `plan_type` (MEDICARE_FFS, MEDICARE_ADVANTAGE, MEDICAID, COMMERCIAL), `member_id_prefix`, `member_id_digits` | Generic names only. Each payer has its own member ID scheme: a prefix, a digit count and a Luhn check digit. Never an MBI shape. |
| `procedures.csv` | `cpt`, `description`, `body_part_examined`, `sided` (0/1), `views`, `modality` (DX) | The exam vocabulary. `body_part_examined` is a DICOM defined term (CHEST, HAND, KNEE and so on). `views` drives E11. |
| `facilities.csv` | `facility_id`, `name`, `npi`, `pos` (31 or 32), `street`, `city`, `state`, `zip`, `county` | Fictitious nursing facilities. `npi` is synthetic and absent from NPPES. |
| `body_part_terms.csv` | `term` | The defined-terms list E03 checks against. |

## Registry (`data/generated/registry/providers.csv`)

| column | note |
|---|---|
| `npi` | 10 digits, Luhn-valid over the 80840 prefix, absent from NPPES (checked by `tests/test_registry.py` against a cached lookup). |
| `entity_type` | 1 individual, 2 organization |
| `role` | ordering_physician, ordering_npp, radiologist, technologist, supplier |
| `family`, `given`, `credential`, `organization_name`, `taxonomy_code`, `taxonomy_label` | NUCC labels. |

## Hop 1. Registration (`registration/patients.csv`, `registration/coverage.csv`, `hl7/adt/*.hl7`)

| table | key | columns |
|---|---|---|
| patients | `mrn` | `mrn`, `synthea_id`, `family`, `given`, `birth_date`, `sex` (M/F), `facility_id`, `admitted` |
| coverage | `coverage_id` | `coverage_id`, `mrn`, `payer_id`, `member_id`, `priority` (1 primary, 2 secondary), `start_date`, `end_date`, `part_a_stay_start`, `part_a_stay_end` (nullable; a Medicare Part A SNF stay window) |

ADT^A04 carries PID-3 (MRN), PID-5, PID-7, PID-8 and one IN1 per coverage row: IN1-1 set ID, IN1-2 plan id, IN1-3 payer id, IN1-4 payer name, IN1-12 effective date, IN1-13 expiration date, IN1-15 plan type, IN1-17 relationship (SEL), IN1-22 coordination-of-benefits priority, IN1-36 policy number (the member ID). Day-level `start_date`/`end_date` are assigned inside the years Synthea gives in `payer_transitions.csv`.

## Hop 2. Order (`orders/orders.csv`, `hl7/orders/*.hl7`)

| column | HL7 (v2.8 OMI^O23 / v2.5.1 ORM^O01) | note |
|---|---|---|
| `placer_order_number` | ORC-2 / OBR-2 | `PLC` + 7 digits |
| `filler_order_number` | ORC-3 / OBR-3 | `FIL` + 7 digits |
| `accession` | IPC-1 (v2.8); OBR-18 (v2.5.1, the IHE convention) | `ACC` + 8 digits. The key of the exam. |
| `mrn` | PID-3 | |
| `trip_id` | the dispatch log | the stop this exam was performed on |
| `order_datetime` | ORC-9 | |
| `scheduled_datetime` | TQ1-7 (v2.8) / ORC-7 (v2.5.1) | |
| `cpt`, `procedure_description` | OBR-4 | CPT code and text |
| `body_part_examined` | from `procedures.csv` | |
| `laterality` | `L`, `R`, `B` or empty | sided procedures only |
| `modifier` | OBR-4 text suffix and the claim line | `LT` or `RT` for sided procedures |
| `ordering_npi` | PRT-5 with PRT-4 = OP (v2.8); ORC-12 / OBR-16 (v2.5.1) | an individual NPI from the registry |
| `reason` | OBR-31 | the statement of the patient's condition (42 CFR 486.106(a)(2)) |
| `views` | derived from `cpt` | expected image count |

## Hop 3. Image (`dicom/<accession>/*.dcm`, extracted to `warehouse/dicom_instances.csv`)

| DICOM tag | column | joins |
|---|---|---|
| (0008,0050) AccessionNumber | `accession` | order |
| (0010,0020) PatientID | `patient_id` | patients.mrn |
| (0010,0010) PatientName, (0010,0030) PatientBirthDate, (0010,0040) PatientSex | `patient_name`, `birth_date`, `sex` | |
| (0020,000D) StudyInstanceUID, (0020,000E) SeriesInstanceUID, (0008,0018) SOPInstanceUID | `study_uid`, `series_uid`, `sop_uid` | |
| (0008,0020) StudyDate, (0008,0030) StudyTime | `study_datetime` | |
| (0018,0015) BodyPartExamined | `body_part_examined` | E03 |
| (0020,0060) Laterality, (0020,0062) ImageLaterality | `laterality`, `image_laterality` | E02 |
| (0018,5101) ViewPosition | `view_position` | AP, PA, LAT |
| (0008,0090) ReferringPhysicianName | `referring_physician` | |
| (0008,0060) Modality | `modality` | DX |

Pixels are synthetic: a 64 x 64 gradient with the word SYNTHETIC drawn from a 5 x 7 bitmap font. No anatomy, no real image.

## Hop 4. Report (`reports/reports.csv`, `hl7/reports/*.hl7`)

| column | HL7 ORU^R01 | note |
|---|---|---|
| `accession` | OBR-18 (v2.5.1); IPC-1 context in v2.8 | |
| `exam_datetime` | OBR-7 | observation date/time |
| `report_datetime` | OBR-22 | results report/status change |
| `status` | OBR-25, OBX-11 | F |
| `text` | OBX-5 | fixed: `SYNTHETIC - NOT A READ` |
| `radiologist_npi` | PRT-5 with PRT-4 = PP (v2.8); OBR-32 (v2.5.1) | |

## Hop 5. FHIR R4 (`fhir/<accession>.json`, extracted to `warehouse/fhir_imagingstudy.csv`, `warehouse/fhir_diagnosticreport.csv`)

ServiceRequest (identifier = placer order), ImagingStudy (identifier type ACSN = accession, `basedOn`, `series.bodySite`, `series.laterality`, `numberOfInstances`), DiagnosticReport (`basedOn`, `imagingStudy`, `effectiveDateTime`, `issued`, `status` final, `conclusion` = the fixed template).

## Hop 6. Claim lines (`claims/claim_lines.csv`)

| column | CMS-1500 / 837P | note |
|---|---|---|
| `claim_line_id`, `claim_id` | | one claim per patient per date of service |
| `accession` | | null on transport lines, which belong to the trip |
| `trip_id` | | |
| `mrn` | | |
| `date_of_service` | 24A | |
| `place_of_service` | 24B | 31 skilled nursing facility, 32 nursing facility |
| `hcpcs` | 24D | CPT for the exam TC; R0070 or R0075 transport; Q0092 set-up |
| `modifiers` | 24D | `TC`; `LT`/`RT`; `UN`,`UP`,`UQ`,`UR`,`US` on R0075 |
| `units` | 24G | 1 |
| `ordering_npi` | 17b | |
| `rendering_npi`, `billing_npi` | 24J, 33a | supplier organization |
| `payer_id`, `member_id` | 1a, 11 | the payer the claim was sent to |
| `charge` | 24F | a flat schedule from `config/`; never a real fee schedule |

## Dispatch log (`trips/trips.csv`)

`trip_id`, `date`, `facility_id`, `technologist_npi`, `patients_seen` (exams on that stop). One transport fee per trip: R0070 when one patient, R0075 with the count modifier when more.

## Truth (`truth/planted_errors.csv`, read by the scorer only)

`record_key`, `record_type` (`accession` for order, report and image plants on a real exam; `study_uid` for an orphan study that has no accession to key on; `claim_line_id` for claim-side plants, including E05 and E06, keyed on the technical-component line), `error_id`, `variant`, `holdout` (0/1), `hop`, `field`, `before`, `after`.
