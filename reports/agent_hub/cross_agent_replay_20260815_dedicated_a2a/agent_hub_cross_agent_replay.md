# Agent Hub cross-Agent relation replay

- Passed: `True`
- Relation Agents: `6`
- Relations: `8`
- Adversarial assertions: `16/16`

| Agent | Relation | Case | Baseline | Detected |
|---|---|---|---|---|
| code-validation | validated_codes_match_medical_coding | value_conflict | yes | yes |
| code-validation | validated_codes_match_medical_coding | ambiguous_upstream | yes | yes |
| compliance-guardrail | reviewed_codes_match_code_validation | value_conflict | yes | yes |
| compliance-guardrail | reviewed_codes_match_code_validation | ambiguous_upstream | yes | yes |
| drg-analyzer | drg_risk_codes_match_compliance_review | value_conflict | yes | yes |
| drg-analyzer | drg_risk_codes_match_compliance_review | ambiguous_upstream | yes | yes |
| evidence_extractor | supported_codes_match_extracted_diagnoses | value_conflict | yes | yes |
| evidence_extractor | supported_codes_match_extracted_diagnoses | ambiguous_upstream | yes | yes |
| medical_coding | coding_primary_matches_principal_review | value_conflict | yes | yes |
| medical_coding | coding_primary_matches_principal_review | ambiguous_upstream | yes | yes |
| medical_coding | coding_secondary_matches_extracted_diagnoses | value_conflict | yes | yes |
| medical_coding | coding_secondary_matches_extracted_diagnoses | ambiguous_upstream | yes | yes |
| medical_coding | coding_procedures_match_extracted_procedures | value_conflict | yes | yes |
| medical_coding | coding_procedures_match_extracted_procedures | ambiguous_upstream | yes | yes |
| principal_diagnosis_review | principal_code_matches_extracted_diagnosis | value_conflict | yes | yes |
| principal_diagnosis_review | principal_code_matches_extracted_diagnosis | ambiguous_upstream | yes | yes |
