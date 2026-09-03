# Agent Hub cross-field relation replay

- Passed: `True`
- Relation Agents: `9`
- Relations: `11`
- Adversarial assertions: `15/15`

| Agent | Relation | Must # | Operator | Baseline | Detected |
|---|---|---:|---|---|---|
| claim-check | missing_policy_requires_review | 0 | equals | yes | yes |
| claim-check | insufficient_evidence_requires_review | 0 | equals | yes | yes |
| clinical-documentation-improvement-agent | withheld_query_requires_human_action | 0 | equals | yes | yes |
| clinical-documentation-improvement-agent | withheld_query_requires_human_action | 1 | equals | yes | yes |
| clinical-education | insufficient_source_requires_limitations | 0 | non_empty | yes | yes |
| clinical-education | insufficient_source_requires_limitations | 1 | equals | yes | yes |
| clinical-guidelines | unmet_guideline_requires_deviation | 0 | non_empty | yes | yes |
| clinical-guidelines | unmet_guideline_requires_deviation | 1 | equals | yes | yes |
| code-validation | failed_validation_requires_review | 0 | equals | yes | yes |
| medical_coding | failed_rules_require_human_review | 0 | equals | yes | yes |
| principal_diagnosis_review | draft_conflict_requires_reason | 0 | non_empty | yes | yes |
| principal_diagnosis_review | draft_conflict_requires_reason | 1 | equals | yes | yes |
| procedure-extractor | procedure_count_matches_items | 0 | length_equals | yes | yes |
| procedure-extractor | procedure_issues_require_review | 0 | equals | yes | yes |
| rule_explainer | review_status_requires_review | 0 | equals | yes | yes |
