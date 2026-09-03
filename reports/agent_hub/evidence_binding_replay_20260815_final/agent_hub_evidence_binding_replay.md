# Agent Hub evidence binding replay

- Passed: `True`
- Binding Agents: `4`
- Bindings: `9`
- Adversarial assertions: `18/18`

| Agent | Binding | Case | Baseline | Detected |
|---|---|---|---|---|
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
| principal_diagnosis_review | principal_candidate_evidence_matches_input | source_text_mismatch | yes | yes |
| principal_diagnosis_review | principal_candidate_evidence_matches_input | out_of_source_bounds | yes | yes |
| procedure-extractor | procedure_evidence_matches_input | source_text_mismatch | yes | yes |
| procedure-extractor | procedure_evidence_matches_input | out_of_source_bounds | yes | yes |
| procedure-extractor | nonbillable_evidence_matches_input | source_text_mismatch | yes | yes |
| procedure-extractor | nonbillable_evidence_matches_input | out_of_source_bounds | yes | yes |
