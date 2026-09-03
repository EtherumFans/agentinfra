# Agent Hub evidence binding replay

- Passed: `True`
- Binding Agents: `6`
- Bindings: `15`
- Adversarial assertions: `30/30`

| Agent | Binding | Case | Baseline | Detected |
|---|---|---|---|---|
| clinical-documentation-improvement-agent | cdi_gap_evidence_matches_document | source_text_mismatch | yes | yes |
| clinical-documentation-improvement-agent | cdi_gap_evidence_matches_document | out_of_source_bounds | yes | yes |
| clinical-documentation-improvement-agent | cdi_query_evidence_matches_document | source_text_mismatch | yes | yes |
| clinical-documentation-improvement-agent | cdi_query_evidence_matches_document | out_of_source_bounds | yes | yes |
| diagnosis-extractor | diagnosis_evidence_matches_input | source_text_mismatch | yes | yes |
| diagnosis-extractor | diagnosis_evidence_matches_input | out_of_source_bounds | yes | yes |
| diagnosis-extractor | noncodable_evidence_matches_input | source_text_mismatch | yes | yes |
| diagnosis-extractor | noncodable_evidence_matches_input | out_of_source_bounds | yes | yes |
| evidence_extractor | supported_evidence_matches_input | source_text_mismatch | yes | yes |
| evidence_extractor | supported_evidence_matches_input | out_of_source_bounds | yes | yes |
| evidence_extractor | uncertain_evidence_matches_input | source_text_mismatch | yes | yes |
| evidence_extractor | uncertain_evidence_matches_input | out_of_source_bounds | yes | yes |
| evidence_extractor | rejected_evidence_matches_input | source_text_mismatch | yes | yes |
| evidence_extractor | rejected_evidence_matches_input | out_of_source_bounds | yes | yes |
| evidence_extractor | coded_evidence_matches_input | source_text_mismatch | yes | yes |
| evidence_extractor | coded_evidence_matches_input | out_of_source_bounds | yes | yes |
| medical_coding | coding_diagnosis_evidence_matches_document | source_text_mismatch | yes | yes |
| medical_coding | coding_diagnosis_evidence_matches_document | out_of_source_bounds | yes | yes |
| medical_coding | coding_procedure_evidence_matches_document | source_text_mismatch | yes | yes |
| medical_coding | coding_procedure_evidence_matches_document | out_of_source_bounds | yes | yes |
| medical_coding | coding_negated_evidence_matches_document | source_text_mismatch | yes | yes |
| medical_coding | coding_negated_evidence_matches_document | out_of_source_bounds | yes | yes |
| medical_coding | coding_history_evidence_matches_document | source_text_mismatch | yes | yes |
| medical_coding | coding_history_evidence_matches_document | out_of_source_bounds | yes | yes |
| principal_diagnosis_review | principal_candidate_evidence_matches_input | source_text_mismatch | yes | yes |
| principal_diagnosis_review | principal_candidate_evidence_matches_input | out_of_source_bounds | yes | yes |
| procedure-extractor | procedure_evidence_matches_input | source_text_mismatch | yes | yes |
| procedure-extractor | procedure_evidence_matches_input | out_of_source_bounds | yes | yes |
| procedure-extractor | nonbillable_evidence_matches_input | source_text_mismatch | yes | yes |
| procedure-extractor | nonbillable_evidence_matches_input | out_of_source_bounds | yes | yes |
