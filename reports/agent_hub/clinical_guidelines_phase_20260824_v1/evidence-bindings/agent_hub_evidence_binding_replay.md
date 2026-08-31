# Agent Hub evidence binding replay

- Passed: `True`
- Binding Agents: `17`
- Bindings: `26`
- Adversarial assertions: `52/52`

| Agent | Binding | Case | Baseline | Detected |
|---|---|---|---|---|
| claim-check | claim_check_evidence_matches_input | source_text_mismatch | yes | yes |
| claim-check | claim_check_evidence_matches_input | out_of_source_bounds | yes | yes |
| clinical-documentation-improvement-agent | cdi_gap_evidence_matches_document | source_text_mismatch | yes | yes |
| clinical-documentation-improvement-agent | cdi_gap_evidence_matches_document | out_of_source_bounds | yes | yes |
| clinical-documentation-improvement-agent | cdi_query_evidence_matches_document | source_text_mismatch | yes | yes |
| clinical-documentation-improvement-agent | cdi_query_evidence_matches_document | out_of_source_bounds | yes | yes |
| clinical-education | clinical_education_evidence_matches_input | source_text_mismatch | yes | yes |
| clinical-education | clinical_education_evidence_matches_input | out_of_source_bounds | yes | yes |
| clinical-guidelines | clinical_guidelines_evidence_matches_input | source_text_mismatch | yes | yes |
| clinical-guidelines | clinical_guidelines_evidence_matches_input | out_of_source_bounds | yes | yes |
| denial-appeals | denial_appeal_evidence_matches_input | source_text_mismatch | yes | yes |
| denial-appeals | denial_appeal_evidence_matches_input | out_of_source_bounds | yes | yes |
| diagnosis-extractor | diagnosis_evidence_matches_input | source_text_mismatch | yes | yes |
| diagnosis-extractor | diagnosis_evidence_matches_input | out_of_source_bounds | yes | yes |
| diagnosis-extractor | noncodable_evidence_matches_input | source_text_mismatch | yes | yes |
| diagnosis-extractor | noncodable_evidence_matches_input | out_of_source_bounds | yes | yes |
| discharge_edu | discharge_education_evidence_matches_input | source_text_mismatch | yes | yes |
| discharge_edu | discharge_education_evidence_matches_input | out_of_source_bounds | yes | yes |
| discharge_summary_structuring | discharge_summary_evidence_matches_input | source_text_mismatch | yes | yes |
| discharge_summary_structuring | discharge_summary_evidence_matches_input | out_of_source_bounds | yes | yes |
| evidence_extractor | located_mention_matches_input | source_text_mismatch | yes | yes |
| evidence_extractor | located_mention_matches_input | out_of_source_bounds | yes | yes |
| icu_summary | icu_summary_evidence_matches_input | source_text_mismatch | yes | yes |
| icu_summary | icu_summary_evidence_matches_input | out_of_source_bounds | yes | yes |
| med_reconciliation | home_medication_evidence_matches_input | source_text_mismatch | yes | yes |
| med_reconciliation | home_medication_evidence_matches_input | out_of_source_bounds | yes | yes |
| med_reconciliation | inpatient_medication_evidence_matches_input | source_text_mismatch | yes | yes |
| med_reconciliation | inpatient_medication_evidence_matches_input | out_of_source_bounds | yes | yes |
| med_reconciliation | discharge_medication_evidence_matches_input | source_text_mismatch | yes | yes |
| med_reconciliation | discharge_medication_evidence_matches_input | out_of_source_bounds | yes | yes |
| med_reconciliation | unresolved_medication_evidence_matches_input | source_text_mismatch | yes | yes |
| med_reconciliation | unresolved_medication_evidence_matches_input | out_of_source_bounds | yes | yes |
| medical_coding | coding_diagnosis_evidence_matches_document | source_text_mismatch | yes | yes |
| medical_coding | coding_diagnosis_evidence_matches_document | out_of_source_bounds | yes | yes |
| medical_coding | coding_procedure_evidence_matches_document | source_text_mismatch | yes | yes |
| medical_coding | coding_procedure_evidence_matches_document | out_of_source_bounds | yes | yes |
| medical_coding | coding_negated_evidence_matches_document | source_text_mismatch | yes | yes |
| medical_coding | coding_negated_evidence_matches_document | out_of_source_bounds | yes | yes |
| medical_coding | coding_history_evidence_matches_document | source_text_mismatch | yes | yes |
| medical_coding | coding_history_evidence_matches_document | out_of_source_bounds | yes | yes |
| nursing_handoff | nursing_handoff_evidence_matches_input | source_text_mismatch | yes | yes |
| nursing_handoff | nursing_handoff_evidence_matches_input | out_of_source_bounds | yes | yes |
| principal_diagnosis_review | principal_candidate_evidence_matches_input | source_text_mismatch | yes | yes |
| principal_diagnosis_review | principal_candidate_evidence_matches_input | out_of_source_bounds | yes | yes |
| prior_auth | prior_authorization_evidence_matches_input | source_text_mismatch | yes | yes |
| prior_auth | prior_authorization_evidence_matches_input | out_of_source_bounds | yes | yes |
| procedure-extractor | procedure_evidence_matches_input | source_text_mismatch | yes | yes |
| procedure-extractor | procedure_evidence_matches_input | out_of_source_bounds | yes | yes |
| procedure-extractor | nonbillable_evidence_matches_input | source_text_mismatch | yes | yes |
| procedure-extractor | nonbillable_evidence_matches_input | out_of_source_bounds | yes | yes |
| referral_gen | referral_evidence_matches_input | source_text_mismatch | yes | yes |
| referral_gen | referral_evidence_matches_input | out_of_source_bounds | yes | yes |
