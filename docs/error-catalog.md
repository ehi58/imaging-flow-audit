# Error catalog

Each error type the flow can plant, the hop where it is planted, the rule that
should catch it, the variants, and the cross-flags the rule is expected to
cause elsewhere. **The rules were written from this catalog before the
injector existed**, and the hold-out variant of each type was added after the
rule was frozen, so recall on the hold-out says whether the rule catches the
error or only the ways of making it that its author had in mind.

The rules live in `dbt/tests/audit/E<nn>_*.sql`. Each is a dbt singular test
with `severity: warn` and `store_failures: true`, so every rule runs, and the
rows it flags are kept for the scorer. The scorer (`score` in `src/flow/audit.py`)
is the only reader of `truth/planted_errors.csv`.

Record keys: an exam is keyed by `accession`; a claim line by `claim_line_id`;
a coverage period by `coverage_id`; a stop by `trip_id`.

## Why these errors cost money

A portable x-ray supplier is paid per exam (the technical component), per trip
(the transport fee, R0070 or R0075 prorated across the patients seen) and per
procedure set-up (Q0092). Every error below either makes a claim deniable,
makes it pay the wrong amount, or leaves work unbilled:

- Identity and order errors (E01, E04, E08) break the chain from a documented
  order to a billed exam. A claim without a valid order from a treating
  practitioner is not payable (42 CFR 410.32(a), 486.106(a)).
- Header errors (E02, E03) make the record of what was done disagree with what
  was billed: a left-side modifier on a right-side image, or an exam with no
  body part, fails a documentation review.
- Coverage errors (E05, E06, E07) send the claim to a payer who will not pay it,
  or to Medicare Part B for a resident in a Part A stay whose imaging belongs on
  the nursing facility's consolidated bill.
- Turnaround errors (E09) are a service-level problem that becomes a billing
  problem when the report never exists: no report, no complete exam.
- View and transport errors (E11, E12) bill the wrong code for what was done:
  two views billed on a one-image study, or a solo-trip transport fee at a stop
  that served several patients.

## The core nine

### E01 — accession number differs between order and image

- **Hop:** image. The DICOM AccessionNumber (0008,0050) is changed after the
  order is written.
- **Rule `E01_accession_mismatch`:** a study whose accession finds no order, or
  finds an order for a different patient or procedure, **while** an unmatched
  order exists for the same MRN, study date and modality. The second clause
  separates a mismatch from an orphan (E04).
- **Variants:** `transposed_digits` (two adjacent digits swapped),
  `prefix_dropped` (`ACC` removed), `other_same_day_accession` (the accession
  of another order on the same day, for a different patient).
- **Hold-out:** `leading_zero_dropped`.
- **Expected cross-flags:** E04 (the study looks orphaned), and the order looks
  unperformed.

### E02 — laterality in the DICOM header disagrees with the order

- **Hop:** image. ImageLaterality (0020,0062) and Laterality (0020,0060) are
  changed.
- **Rule `E02_laterality_disagrees`:** for sided body parts, the order modifier
  (LT = L, RT = R) must equal ImageLaterality, with Laterality as the fallback
  when ImageLaterality is empty. Chest is unpaired, so an empty value there is
  correct and is the negative control inside the rule.
- **Variants:** `lr_swapped`, `image_laterality_blank` (on a sided body part,
  with Laterality also blank), `bilateral_on_single` (B on a one-side order).
- **Hold-out:** `laterality_tag_only_wrong` (ImageLaterality correct,
  Laterality wrong; the rule's fallback order decides whether it fires).

### E03 — missing body part

- **Hop:** image. BodyPartExamined (0018,0015).
- **Rule `E03_body_part_missing_or_undefined`:** the tag must be present,
  non-empty, and in `data/vocab/body_part_terms.csv`.
- **Variants:** `tag_absent`, `tag_empty`, `undefined_term` (a value not in the
  list).
- **Hold-out:** `lowercase_term` (a defined term in the wrong case).

### E04 — image with no order

- **Hop:** image.
- **Rule `E04_study_without_order`:** the study has no order on accession
  **and** no candidate order for the same MRN, study date and modality.
- **Variants:** `never_ordered_accession` (an accession no order carries),
  `blank_accession`, `mrn_without_orders` (a study for a registered patient who
  has no orders at all).
- **Hold-out:** `cancelled_order_accession` (the accession of an order whose
  control code is CA).
- **Expected cross-flags:** none by design; E01 is excluded by the candidate
  clause.

### E05 — wrong or invalid insurance ID

- **Hop:** registration, carried to the claim. The member ID in IN1-36 and on
  the claim line.
- **Rule `E05_member_id_invalid`:** the member ID on the claim must match its
  payer's scheme (prefix, digit count, Luhn check digit) and belong to this
  patient's coverage on the date of service.
- **Variants:** `wrong_payer_prefix`, `failed_check_digit`, `other_members_id`
  (a valid ID that belongs to another patient).
- **Hold-out:** `truncated_id` (one digit short).

### E06 — coverage expired or not yet started on the date of service

- **Hop:** registration (the coverage period), observed on the claim.
- **Rule `E06_coverage_not_in_force`:** a range join of the claim's date of
  service to the patient's coverage periods for the billed payer; no covering
  period means a flag.
- **Variants:** `after_coverage_end`, `before_coverage_start`,
  `end_day_before_service` (the period ends the day before the exam).
- **Hold-out:** `gap_between_periods` (two periods with a gap, the exam in the
  gap).

### E07 — payer wrong for the date of service

- **Hop:** claim.
- **Rule `E07_wrong_payer`:** the expected primary payer from coverage on the
  date of service must equal the payer on the claim.
- **Variants:** `ffs_billed_while_ma` (Medicare fee-for-service billed while
  the resident is in a Medicare Advantage plan), `medicaid_primary_for_dual`
  (Medicaid billed as primary for a dual-eligible), `prior_payer_after_switch`
  (the payer from before a plan switch).
- **Hold-out:** `secondary_billed_as_primary`.
- **Not encoded:** Part B billing during a covered Part A stay. The code-level
  rule must be confirmed against the CMS SNF consolidated billing annual update
  first; until then the Part A stay window is carried in the data and no rule
  reads it.

### E08 — ordering-provider NPI missing or invalid

- **Hop:** order, carried to the claim (box 17b).
- **Rule `E08_ordering_npi_invalid`:** present, Luhn-valid over the 80840
  prefix, and an individual (entity type 1) in the synthetic registry.
- **Variants:** `blank`, `failed_check_digit`, `organization_npi` (a registry
  organization where an individual is required).
- **Hold-out:** `unregistered_valid_npi` (Luhn-valid, not in the registry).

### E09 — report turnaround outlier

- **Hop:** report.
- **Rule `E09_report_turnaround`:** report time minus exam time beyond the SLA
  in `config/error_rates.yaml` (`sla.report_turnaround_hours`), or negative, or
  no report at all (an anti-join of exams to reports).
- **Variants:** `beyond_sla`, `report_before_exam`, `no_report`.
- **Hold-out:** `report_at_sla_plus_one_minute` (a boundary case).

## Two reconciliation types (ruled in on 2026-10-18)

### E11 — views billed differ from views taken

- **Hop:** claim. The CPT on the exam's technical-component line.
- **Rule `E11_views_billed_vs_taken`:** the instance count of the study must
  equal the view count the billed CPT implies (`data/vocab/procedures.csv`):
  71046 is two views, 71045 is one.
- **Variants:** `two_view_billed_one_image`, `single_view_billed_two_images`.
- **Hold-out:** `three_views_billed_two_images` (a three-view code on a
  two-image study).

### E12 — transport line inconsistent with the stop

- **Hop:** claim. The R0070/R0075 line for a trip.
- **Rule `E12_transport_vs_stop`:** group the exams by trip; one patient means
  R0070; more than one means R0075 with the modifier for the count (UN 2, UP 3,
  UQ 4, UR 5, US 6 or more); a transport line on a trip with no exam is a flag
  (Medicare Claims Processing Manual, ch. 13, §90.3.4).
- **Variants:** `r0075_single_patient`, `r0070_multi_patient`,
  `transport_without_exam`.
- **Hold-out:** `modifier_count_mismatch` (R0075 with UP at a two-patient stop).

## Cascades

A plant at the coverage grain, the claim grain or on another exam's accession
changes more than the one record its truth row names, and a rule that fires on
the others is right:

| plant | what else it reaches | rules that may fire there |
|---|---|---|
| E05, any variant | every claim line of that patient and payer now carries the bad member ID; for `other_members_id`, every claim line of the member whose ID was borrowed as well | E05 (the ID is shared by two patients) |
| E06, any variant | every claim line of that patient and payer, because the coverage period itself was shortened or split | E06 (later or earlier claims now fall outside it) |
| E07, any variant | every line of the claim, because the whole claim went to the wrong payer | E07, E05 (the member ID no longer fits the payer's scheme) |
| E01 `other_same_day_accession`, or any E01 variant whose new accession happens to be a real one | the exam that now holds an image it never took | E01, E11 (two images against one view billed) |

The injector writes a truth row for each of those records with `hop = cascade`
and no before/after of its own, carrying the error id and variant of the plant
that caused it. The scorer never counts a cascade row as planted: recall is
caught over the direct rows, hold-outs apart. Every flag a rule raises is then
one of four things, and the report has a column for each: a **plant** (caught),
a **cascade flag**, a **cross-flag** on a record planted with a different error
(the "expected cross-flags" listed per type above), or **unexplained**. The
target for the last column is zero, and `tests/test_cascade_truth.py` holds it
there.

Measured before cascades were written down (24 months, seed 20261101): E05
raised 1,134 flags on records no truth row named, E06 670, E07 197 and E11 38,
and the report called them "flags matching no plant". Every one was one of the
four mechanisms above.

## Controls

- **Clean run** (`--clean`): the injector plants nothing. Every flag is a false
  positive or a generator defect, and the count is the documented baseline in
  `reports/recall.md`.
- **Injected run:** every rule must flag at least one row; a rule that flags
  nothing fails `tests/test_audit.py`.
- **Vocabulary controls** run before any rule: every code in the procedure,
  body-part and payer vocabularies occurs in the generated data, and every
  generated code is in its vocabulary.
- **Hold-out variants** are scored separately from the variants the rules were
  written against.
