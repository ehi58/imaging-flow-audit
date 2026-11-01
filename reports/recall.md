# Recall per error type

These numbers measure the rules on synthetic data with known planted errors. They are not results from any client.

Recall is caught ÷ planted over the core variants. Hold-out variants were written after the rules were frozen and are scored apart.

| rule | planted | caught | recall | 95% interval | hold-out planted | hold-out caught | cascade flags | cross-flags on other plants | unexplained flags |
|---|---:|---:|---:|---|---:|---:|---:|---:|---:|
| E01 | 114 | 114 | 1.00 | 0.97 to 1.00 | 38 | 38 | 0 | 1 | 0 |
| E02 | 30 | 30 | 1.00 | 0.89 to 1.00 | 9 | 0 | 0 | 14 | 0 |
| E03 | 75 | 75 | 1.00 | 0.95 to 1.00 | 24 | 24 | 0 | 0 | 0 |
| E04 | 60 | 59 | 0.98 | 0.91 to 1.00 | 20 | 20 | 0 | 0 | 0 |
| E05 | 45 | 45 | 1.00 | 0.92 to 1.00 | 15 | 15 | 1133 | 25 | 0 |
| E06 | 107 | 103 | 0.96 | 0.91 to 0.99 | 36 | 36 | 669 | 51 | 0 |
| E07 | 75 | 75 | 1.00 | 0.95 to 1.00 | 25 | 24 | 198 | 0 | 0 |
| E08 | 114 | 114 | 1.00 | 0.97 to 1.00 | 38 | 38 | 0 | 0 | 0 |
| E09 | 76 | 76 | 1.00 | 0.95 to 1.00 | 25 | 25 | 0 | 0 | 0 |
| E11 | 68 | 67 | 0.99 | 0.92 to 1.00 | 34 | 33 | 36 | 2 | 0 |
| E12 | 75 | 75 | 1.00 | 0.95 to 1.00 | 25 | 25 | 0 | 0 | 0 |

## Per variant

| rule | variant | hold-out | planted | caught | recall |
|---|---|---|---:|---:|---:|
| E01 | transposed_digits |  | 38 | 38 | 1.00 |
| E01 | prefix_dropped |  | 38 | 38 | 1.00 |
| E01 | other_same_day_accession |  | 38 | 38 | 1.00 |
| E01 | leading_zero_dropped | yes | 38 | 38 | 1.00 |
| E02 | lr_swapped |  | 10 | 10 | 1.00 |
| E02 | image_laterality_blank |  | 10 | 10 | 1.00 |
| E02 | bilateral_on_single |  | 10 | 10 | 1.00 |
| E02 | laterality_tag_only_wrong | yes | 9 | 0 | 0.00 |
| E03 | tag_absent |  | 25 | 25 | 1.00 |
| E03 | tag_empty |  | 25 | 25 | 1.00 |
| E03 | undefined_term |  | 25 | 25 | 1.00 |
| E03 | lowercase_term | yes | 24 | 24 | 1.00 |
| E04 | never_ordered_accession |  | 20 | 20 | 1.00 |
| E04 | blank_accession |  | 20 | 19 | 0.95 |
| E04 | mrn_without_orders |  | 20 | 20 | 1.00 |
| E04 | cancelled_order_accession | yes | 20 | 20 | 1.00 |
| E05 | wrong_payer_prefix |  | 15 | 15 | 1.00 |
| E05 | failed_check_digit |  | 15 | 15 | 1.00 |
| E05 | other_members_id |  | 15 | 15 | 1.00 |
| E05 | truncated_id | yes | 15 | 15 | 1.00 |
| E06 | after_coverage_end |  | 34 | 34 | 1.00 |
| E06 | before_coverage_start |  | 37 | 36 | 0.97 |
| E06 | end_day_before_service |  | 36 | 33 | 0.92 |
| E06 | gap_between_periods | yes | 36 | 36 | 1.00 |
| E07 | ffs_billed_while_ma |  | 25 | 25 | 1.00 |
| E07 | medicaid_primary_for_dual |  | 25 | 25 | 1.00 |
| E07 | prior_payer_after_switch |  | 25 | 25 | 1.00 |
| E07 | secondary_billed_as_primary | yes | 25 | 24 | 0.96 |
| E08 | blank |  | 38 | 38 | 1.00 |
| E08 | failed_check_digit |  | 38 | 38 | 1.00 |
| E08 | organization_npi |  | 38 | 38 | 1.00 |
| E08 | unregistered_valid_npi | yes | 38 | 38 | 1.00 |
| E09 | beyond_sla |  | 26 | 26 | 1.00 |
| E09 | report_before_exam |  | 25 | 25 | 1.00 |
| E09 | no_report |  | 25 | 25 | 1.00 |
| E09 | report_at_sla_plus_one_minute | yes | 25 | 25 | 1.00 |
| E11 | two_view_billed_one_image |  | 34 | 34 | 1.00 |
| E11 | single_view_billed_two_images |  | 34 | 33 | 0.97 |
| E11 | three_views_billed_two_images | yes | 34 | 33 | 0.97 |
| E12 | r0075_single_patient |  | 25 | 25 | 1.00 |
| E12 | r0070_multi_patient |  | 25 | 25 | 1.00 |
| E12 | transport_without_exam |  | 25 | 25 | 1.00 |
| E12 | modifier_count_mismatch | yes | 25 | 25 | 1.00 |

Recall = caught ÷ planted over the core variants of each rule; the interval is Wilson, 95%. A **cascade flag** is on a record the plant was expected to reach without being the planted record: the patient's other claim lines after a coverage or member-ID change, the other lines of a claim sent to the wrong payer, the exam that gained an image (docs/error-catalog.md). A **cross-flag** is on a record planted with a different error. An **unexplained flag** is a false positive or a mechanism nobody has written down; the target is zero.
