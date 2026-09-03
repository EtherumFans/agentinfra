# Agent Hub cross-field relation replay

- Passed: `False`
- Relation Agents: `11`
- Relations: `34`
- Adversarial assertions: `59/59`

| Agent | Relation | Must # | Operator | Baseline | Detected |
|---|---|---:|---|---|---|
| claim-check | missing_policy_requires_review | 0 | equals | yes | yes |
| claim-check | insufficient_evidence_requires_review | 0 | equals | yes | yes |
| clinical-documentation-improvement-agent | withheld_query_requires_human_action | 0 | equals | yes | yes |
| clinical-documentation-improvement-agent | withheld_query_requires_human_action | 1 | equals | yes | yes |
| clinical-documentation-improvement-agent | draft_queries_require_traceable_content | 0 | non_empty | yes | yes |
| clinical-documentation-improvement-agent | draft_queries_require_traceable_content | 1 | non_empty | yes | yes |
| clinical-documentation-improvement-agent | draft_queries_require_traceable_content | 2 | non_empty | yes | yes |
| clinical-documentation-improvement-agent | draft_queries_require_traceable_content | 3 | non_empty | yes | yes |
| clinical-documentation-improvement-agent | draft_queries_require_traceable_content | 4 | non_empty | yes | yes |
| clinical-education | insufficient_source_requires_limitations | 0 | non_empty | yes | yes |
| clinical-education | insufficient_source_requires_limitations | 1 | equals | yes | yes |
| clinical-guidelines | unmet_guideline_requires_deviation | 0 | non_empty | yes | yes |
| clinical-guidelines | unmet_guideline_requires_deviation | 1 | equals | yes | yes |
| clinical-guidelines | unmet_criterion_requires_deviation | 0 | non_empty | yes | yes |
| clinical-guidelines | unmet_criterion_requires_deviation | 1 | non_empty | yes | yes |
| clinical-guidelines | unassessable_criterion_requires_uncertainty | 0 | non_empty | yes | yes |
| code-validation | failed_validation_requires_review | 0 | equals | yes | yes |
| code-validation | valid_code_requires_catalog_assignability | 0 | equals | yes | yes |
| code-validation | valid_code_requires_catalog_assignability | 1 | equals | yes | yes |
| code-validation | invalid_code_requires_issue | 0 | equals | yes | yes |
| code-validation | invalid_code_requires_issue | 1 | non_empty | yes | yes |
| diagnosis-extractor | codable_diagnosis_requires_current_evidence | 0 | equals | yes | yes |
| diagnosis-extractor | codable_diagnosis_requires_current_evidence | 1 | non_empty | yes | yes |
| diagnosis-extractor | codable_diagnosis_requires_current_evidence | 2 | non_empty | yes | yes |
| diagnosis-extractor | codable_diagnosis_requires_current_evidence | 3 | non_empty | yes | yes |
| diagnosis-extractor | noncodable_mention_requires_reason | 0 | in | yes | yes |
| diagnosis-extractor | noncodable_mention_requires_reason | 1 | non_empty | yes | yes |
| diagnosis-extractor | noncodable_mention_requires_reason | 2 | non_empty | yes | yes |
| diagnosis-extractor | codable_and_noncodable_evidence_are_disjoint | 0 | disjoint_fields | yes | yes |
| evidence_extractor | supported_code_requires_direct_high_confidence_evidence | 0 | equals | yes | yes |
| evidence_extractor | supported_code_requires_direct_high_confidence_evidence | 1 | gte | yes | yes |
| evidence_extractor | supported_code_requires_direct_high_confidence_evidence | 2 | non_empty | yes | yes |
| evidence_extractor | supported_code_requires_direct_high_confidence_evidence | 3 | non_empty | yes | yes |
| evidence_extractor | uncertain_low_confidence_requires_review_prompt | 0 | non_empty | yes | yes |
| evidence_extractor | uncertain_risk_strength_requires_review_prompt | 0 | non_empty | yes | yes |
| evidence_extractor | rejected_low_confidence_requires_review_prompt | 0 | non_empty | yes | yes |
| evidence_extractor | rejected_risk_strength_requires_review_prompt | 0 | non_empty | yes | yes |
| evidence_extractor | supported_and_uncertain_codes_are_disjoint | 0 | disjoint_fields | yes | yes |
| evidence_extractor | supported_and_rejected_codes_are_disjoint | 0 | disjoint_fields | yes | yes |
| evidence_extractor | uncertain_and_rejected_codes_are_disjoint | 0 | disjoint_fields | yes | yes |
| medical_coding | failed_rules_require_human_review | 0 | equals | yes | yes |
| principal_diagnosis_review | draft_conflict_requires_reason | 0 | non_empty | yes | yes |
| principal_diagnosis_review | draft_conflict_requires_reason | 1 | equals | yes | yes |
| principal_diagnosis_review | recommended_candidate_requires_evidence | 0 | non_empty | yes | yes |
| principal_diagnosis_review | recommended_candidate_requires_evidence | 1 | non_empty | yes | yes |
| principal_diagnosis_review | recommended_candidate_requires_evidence | 2 | non_empty | yes | yes |
| principal_diagnosis_review | nonrecommended_candidate_requires_rationale | 0 | non_empty | no | yes |
| principal_diagnosis_review | exactly_one_principal_candidate_recommended | 0 | count_where_equals | yes | yes |
| principal_diagnosis_review | recommended_principal_matches_flagged_candidate | 0 | contains_field_equals_path | yes | yes |
| procedure-extractor | procedure_count_matches_items | 0 | length_equals | yes | yes |
| procedure-extractor | billable_procedure_requires_performed_evidence | 0 | equals | yes | yes |
| procedure-extractor | billable_procedure_requires_performed_evidence | 1 | non_empty | yes | yes |
| procedure-extractor | billable_procedure_requires_performed_evidence | 2 | non_empty | yes | yes |
| procedure-extractor | billable_procedure_requires_performed_evidence | 3 | non_empty | yes | yes |
| procedure-extractor | nonbillable_procedure_requires_status_evidence | 0 | in | yes | yes |
| procedure-extractor | nonbillable_procedure_requires_status_evidence | 1 | non_empty | yes | yes |
| procedure-extractor | billable_and_nonbillable_evidence_are_disjoint | 0 | disjoint_fields | yes | yes |
| procedure-extractor | procedure_issues_require_review | 0 | equals | yes | yes |
| rule_explainer | review_status_requires_review | 0 | equals | yes | yes |
