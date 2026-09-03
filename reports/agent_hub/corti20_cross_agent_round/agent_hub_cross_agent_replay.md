# Agent Hub cross-Agent relation replay

- Passed: `True`
- Relation Agents: `3`
- Relations: `3`
- Adversarial assertions: `6/6`

| Agent | Relation | Case | Baseline | Detected |
|---|---|---|---|---|
| evidence_extractor | supported_codes_match_extracted_diagnoses | value_conflict | yes | yes |
| evidence_extractor | supported_codes_match_extracted_diagnoses | ambiguous_upstream | yes | yes |
| medical_coding | coding_primary_matches_principal_review | value_conflict | yes | yes |
| medical_coding | coding_primary_matches_principal_review | ambiguous_upstream | yes | yes |
| principal_diagnosis_review | principal_code_matches_extracted_diagnosis | value_conflict | yes | yes |
| principal_diagnosis_review | principal_code_matches_extracted_diagnosis | ambiguous_upstream | yes | yes |
