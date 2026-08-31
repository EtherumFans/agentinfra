from icoder_runtime.backends.output_contract_validation import (
    apply_declared_constants,
    declared_contract_fields,
    json_type_name,
    prepare_source_documents,
    validate_cross_agent_relations,
    validate_cross_agent_relations_definition,
    validate_declared_field_schemas,
    validate_evidence_bindings,
    validate_evidence_bindings_definition,
    validate_field_relations_definition,
    validate_field_schema_definition,
    validate_required_field_types,
    value_matches_type,
)


def test_json_types_distinguish_boolean_integer_and_number() -> None:
    assert json_type_name(True) == "boolean"
    assert json_type_name(2) == "integer"
    assert json_type_name(0.5) == "number"
    assert value_matches_type(True, "integer") is False
    assert value_matches_type(True, "number") is False
    assert value_matches_type(2, "number") is True
    assert value_matches_type(float("nan"), "number") is False
    assert value_matches_type(float("inf"), "number") is False
    assert json_type_name(float("nan")) == "non_finite_number"


def test_validation_reports_metadata_only_for_present_required_fields() -> None:
    secret = "patient-secret-marker"
    contract = {
        "required_fields": ["summary", "issues", "missing"],
        "field_types": {
            "summary": "string",
            "issues": "array",
            "missing": "object",
        },
    }

    violations = validate_required_field_types(
        {"summary": secret, "issues": {"value": secret}},
        contract,
    )

    assert [item.to_dict() for item in violations] == [
        {"field": "issues", "expected": "array", "actual": "object"}
    ]
    assert secret not in repr(violations)


def test_optional_declared_fields_are_included_in_type_validation() -> None:
    contract = {
        "required_fields": ["summary"],
        "optional_fields": ["details"],
        "field_types": {"summary": "string", "details": "array"},
    }

    assert declared_contract_fields(contract) == ["summary", "details"]
    assert [
        item.to_dict()
        for item in validate_required_field_types(
            {"summary": "review", "details": {}},
            contract,
        )
    ] == [{"field": "details", "expected": "array", "actual": "object"}]


def test_declared_constants_override_model_claims_and_fill_optional_governance() -> None:
    contract = {
        "required_fields": ["manual_review_required"],
        "optional_fields": ["billing_authoritative", "rule_authority_status"],
        "field_types": {
            "manual_review_required": "boolean",
            "billing_authoritative": "boolean",
            "rule_authority_status": "string",
        },
        "field_schemas": {
            "manual_review_required": {"type": "boolean", "const": True},
            "billing_authoritative": {"type": "boolean", "const": False},
            "rule_authority_status": {
                "type": "string",
                "const": "experimental_unverified",
            },
        },
    }

    normalized = apply_declared_constants(
        {
            "manual_review_required": False,
            "billing_authoritative": True,
            "undeclared": "preserved-for-separate-rejection",
        },
        contract,
    )

    assert normalized["manual_review_required"] is True
    assert normalized["billing_authoritative"] is False
    assert normalized["rule_authority_status"] == "experimental_unverified"
    assert normalized["undeclared"] == "preserved-for-separate-rejection"


def test_recursive_schema_reports_declared_paths_without_values_or_unknown_keys() -> None:
    secret_value = "patient-secret-marker"
    secret_key = "patient-name-as-key"
    contract = {
        "required_fields": ["evidence"],
        "field_types": {"evidence": "array"},
        "field_schemas": {
            "evidence": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "confidence": {"type": "number"},
                    },
                    "required": ["text", "confidence"],
                    "additionalProperties": False,
                },
            }
        },
    }

    violations = validate_declared_field_schemas(
        {
            "evidence": [{
                "text": secret_value,
                "confidence": "high",
                secret_key: secret_value,
            }]
        },
        contract,
    )

    assert [item.to_dict() for item in violations] == [
        {
            "path": "evidence[]",
            "keyword": "additionalProperties",
            "expected": "none",
            "actual": "undeclared_property",
        },
        {
            "path": "evidence[].confidence",
            "keyword": "type",
            "expected": "number",
            "actual": "string",
        },
    ]
    assert secret_value not in repr(violations)
    assert secret_key not in repr(violations)


def test_schema_definition_requires_closed_typed_complex_shapes() -> None:
    assert validate_field_schema_definition(
        {
            "type": "object",
            "properties": {"items": {"type": "array"}},
            "required": ["missing"],
            "additionalProperties": True,
        },
        path="field_schemas.review",
        expected_root_type="array",
    ) == [
        "field_schemas.review.type must match field_types (array)",
        "field_schemas.review.required contains undeclared properties",
        "field_schemas.review.additionalProperties must be false or a typed schema",
        "field_schemas.review.items.items must be a typed schema",
    ]


def test_semantic_constraints_accept_valid_values() -> None:
    contract = {
        "required_fields": ["status", "manual_review_required", "evidence"],
        "field_types": {
            "status": "string",
            "manual_review_required": "boolean",
            "evidence": "array",
        },
        "field_schemas": {
            "status": {"type": "string", "enum": ["PASS", "WARNING"], "maxLength": 16},
            "manual_review_required": {"type": "boolean", "const": True},
            "evidence": {
                "type": "array",
                "minItems": 1,
                "maxItems": 2,
                "uniqueItems": True,
                "items": {
                    "type": "object",
                    "properties": {
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "char_span": {
                            "type": "array",
                            "minItems": 2,
                            "maxItems": 2,
                            "x-order": "nondecreasing",
                            "items": {"type": "integer", "minimum": 0},
                        },
                    },
                    "required": ["confidence", "char_span"],
                    "additionalProperties": False,
                },
            },
        },
    }

    assert validate_declared_field_schemas(
        {
            "status": "PASS",
            "manual_review_required": True,
            "evidence": [{"confidence": 0.8, "char_span": [3, 9]}],
        },
        contract,
    ) == []


def test_semantic_constraint_failures_are_phi_safe() -> None:
    secret = "patient-secret-value"
    contract = {
        "required_fields": ["status", "manual_review_required", "confidence", "span"],
        "field_types": {
            "status": "string",
            "manual_review_required": "boolean",
            "confidence": "number",
            "span": "array",
        },
        "field_schemas": {
            "status": {"type": "string", "enum": ["PASS"], "maxLength": 4},
            "manual_review_required": {"type": "boolean", "const": True},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "span": {
                "type": "array",
                "minItems": 2,
                "maxItems": 2,
                "uniqueItems": True,
                "x-order": "nondecreasing",
                "items": {"type": "integer", "minimum": 0},
            },
        },
    }

    violations = validate_declared_field_schemas(
        {
            "status": secret,
            "manual_review_required": False,
            "confidence": 1.2,
            "span": [4, -1, -1],
        },
        contract,
    )
    keywords = {item.keyword for item in violations}
    assert {"enum", "maxLength", "const", "maximum", "maxItems", "uniqueItems", "x-order", "minimum"} <= keywords
    assert secret not in repr(violations)


def test_schema_definition_rejects_malformed_semantic_constraints() -> None:
    errors = validate_field_schema_definition(
        {
            "type": "array",
            "minItems": 3,
            "maxItems": 1,
            "uniqueItems": "yes",
            "x-order": "descending",
            "items": {"type": "string", "minimum": 0},
        },
        path="field_schemas.values",
        expected_root_type="array",
    )

    assert any("minItems must not exceed maxItems" in error for error in errors)
    assert any("uniqueItems must be boolean" in error for error in errors)
    assert any("x-order is unsupported" in error for error in errors)
    assert any("numeric bounds require integer or number type" in error for error in errors)
    assert validate_field_schema_definition(
        {"type": "string", "unknownKeyword": True},
        path="field_schemas.value",
    ) == ["field_schemas.value contains unsupported keywords: unknownKeyword"]


def _relation_contract() -> dict:
    return {
        "required_fields": ["status", "items", "total_count", "review"],
        "field_types": {
            "status": "string",
            "items": "array",
            "total_count": "integer",
            "review": "object",
        },
        "field_schemas": {
            "status": {"type": "string"},
            "items": {"type": "array", "items": {"type": "string"}},
            "total_count": {"type": "integer"},
            "review": {
                "type": "object",
                "properties": {"required": {"type": "boolean"}},
                "required": ["required"],
                "additionalProperties": False,
            },
        },
        "field_relations": [
            {
                "id": "item_count_matches",
                "when": [{"path": "items", "operator": "present"}],
                "must": [{
                    "path": "items",
                    "operator": "length_equals",
                    "other_path": "total_count",
                }],
            },
            {
                "id": "warning_requires_review",
                "when": [{"path": "status", "operator": "equals", "value": "WARNING"}],
                "must": [{
                    "path": "review.required",
                    "operator": "equals",
                    "value": True,
                }],
            },
        ],
    }


def test_cross_field_relations_accept_consistent_output() -> None:
    contract = _relation_contract()

    assert validate_field_relations_definition(contract) == []
    assert validate_declared_field_schemas(
        {
            "status": "WARNING",
            "items": ["one", "two"],
            "total_count": 2,
            "review": {"required": True},
        },
        contract,
    ) == []


def test_cross_field_relation_failures_are_phi_safe() -> None:
    secret = "patient-secret-cross-field-marker"
    contract = _relation_contract()

    violations = validate_declared_field_schemas(
        {
            "status": "WARNING",
            "items": [secret],
            "total_count": 2,
            "review": {"required": False},
        },
        contract,
    )

    assert [item.to_dict() for item in violations] == [
        {
            "path": "items",
            "keyword": "fieldRelation",
            "expected": "item_count_matches",
            "actual": "length_equals_violated",
        },
        {
            "path": "review.required",
            "keyword": "fieldRelation",
            "expected": "warning_requires_review",
            "actual": "equals_violated",
        },
    ]
    assert secret not in repr(violations)


def test_cross_field_relation_definition_rejects_unsafe_or_untyped_rules() -> None:
    contract = _relation_contract()
    contract["field_relations"] = [
        {
            "id": "Bad Id",
            "when": [{"path": "unknown", "operator": "equals", "value": True}],
            "must": [{"path": "items", "operator": "length_equals", "other_path": "status"}],
        },
        {
            "id": "duplicate_rule",
            "when": [{"path": "status", "operator": "present", "value": "forbidden"}],
            "must": [{"path": "review.required", "operator": "execute_code"}],
        },
    ]

    errors = validate_field_relations_definition(contract)

    assert any("stable lowercase identifier" in error for error in errors)
    assert any("path must resolve" in error for error in errors)
    assert any("requires array and integer paths" in error for error in errors)
    assert any("present does not accept" in error for error in errors)
    assert any("operator is unsupported" in error for error in errors)


def test_per_item_relations_validate_every_item_and_keep_paths_phi_safe() -> None:
    contract = {
        "required_fields": ["candidates"],
        "field_types": {"candidates": "array"},
        "field_schemas": {
            "candidates": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "enum": ["supported", "rejected"]},
                        "strength": {"type": "string"},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "evidence": {"type": "string"},
                    },
                    "required": ["status", "strength", "confidence", "evidence"],
                    "additionalProperties": False,
                },
            }
        },
        "field_relations": [
            {
                "id": "supported_item_requires_direct_evidence",
                "for_each": "candidates",
                "when": [{"path": "status", "operator": "equals", "value": "supported"}],
                "must": [
                    {"path": "strength", "operator": "in", "value": ["direct"]},
                    {"path": "confidence", "operator": "gte", "value": 0.7},
                    {"path": "evidence", "operator": "non_empty"},
                ],
            }
        ],
    }

    assert validate_field_relations_definition(contract) == []
    violations = validate_declared_field_schemas(
        {
            "candidates": [
                {
                    "status": "supported",
                    "strength": "direct",
                    "confidence": 0.9,
                    "evidence": "safe first item",
                },
                {
                    "status": "supported",
                    "strength": "indirect-secret-marker",
                    "confidence": 0.2,
                    "evidence": "",
                },
            ]
        },
        contract,
    )

    assert [item.to_dict() for item in violations] == [
        {
            "path": "candidates[].strength",
            "keyword": "fieldRelation",
            "expected": "supported_item_requires_direct_evidence",
            "actual": "in_violated",
        },
        {
            "path": "candidates[].confidence",
            "keyword": "fieldRelation",
            "expected": "supported_item_requires_direct_evidence",
            "actual": "gte_violated",
        },
        {
            "path": "candidates[].evidence",
            "keyword": "fieldRelation",
            "expected": "supported_item_requires_direct_evidence",
            "actual": "non_empty_violated",
        },
    ]
    assert "secret-marker" not in repr(violations)


def test_per_item_relation_definition_rejects_non_object_scope_and_bad_numeric_path() -> None:
    contract = _relation_contract()
    contract["field_relations"] = [{
        "id": "bad_item_scope",
        "for_each": "items",
        "when": [{"path": "status", "operator": "present"}],
        "must": [{"path": "status", "operator": "gte", "value": "high"}],
    }]

    errors = validate_field_relations_definition(contract)

    assert any("for_each must resolve to an array of declared objects" in error for error in errors)
    assert any("gte requires a numeric path" in error for error in errors)


def _set_relation_contract() -> dict:
    candidate_item = {
        "type": "object",
        "properties": {
            "code": {"type": "string"},
            "recommended": {"type": "boolean"},
            "evidence": {"type": "string"},
        },
        "required": ["code", "recommended", "evidence"],
        "additionalProperties": False,
    }
    rejected_item = {
        "type": "object",
        "properties": {"evidence": {"type": "string"}},
        "required": ["evidence"],
        "additionalProperties": False,
    }
    return {
        "required_fields": ["candidates", "recommended", "rejected"],
        "field_types": {
            "candidates": "array", "recommended": "object", "rejected": "array",
        },
        "field_schemas": {
            "candidates": {"type": "array", "items": candidate_item},
            "recommended": {
                "type": "object",
                "properties": {"code": {"type": "string"}},
                "required": ["code"],
                "additionalProperties": False,
            },
            "rejected": {"type": "array", "items": rejected_item},
        },
        "field_relations": [
            {
                "id": "exactly_one_recommended_candidate",
                "when": [{"path": "candidates", "operator": "present"}],
                "must": [{
                    "path": "candidates",
                    "operator": "count_where_equals",
                    "where": [{"path": "recommended", "operator": "equals", "value": True}],
                    "value": 1,
                }],
            },
            {
                "id": "recommended_code_matches_flagged_candidate",
                "when": [{"path": "recommended.code", "operator": "present"}],
                "must": [{
                    "path": "candidates",
                    "operator": "contains_field_equals_path",
                    "where": [{"path": "recommended", "operator": "equals", "value": True}],
                    "item_path": "code",
                    "other_path": "recommended.code",
                }],
            },
            {
                "id": "accepted_and_rejected_evidence_are_disjoint",
                "when": [{"path": "candidates", "operator": "present"}],
                "must": [{
                    "path": "candidates",
                    "operator": "disjoint_fields",
                    "item_path": "evidence",
                    "other_path": "rejected",
                    "other_item_path": "evidence",
                }],
            },
        ],
    }


def test_set_relations_accept_consistent_collections() -> None:
    contract = _set_relation_contract()

    assert validate_field_relations_definition(contract) == []
    assert validate_declared_field_schemas(
        {
            "candidates": [
                {"code": "A", "recommended": True, "evidence": "accepted-a"},
                {"code": "B", "recommended": False, "evidence": "accepted-b"},
            ],
            "recommended": {"code": "A"},
            "rejected": [{"evidence": "rejected-c"}],
        },
        contract,
    ) == []


def test_set_relation_failures_are_phi_safe() -> None:
    secret = "patient-secret-set-marker"
    violations = validate_declared_field_schemas(
        {
            "candidates": [
                {"code": "A", "recommended": True, "evidence": secret},
                {"code": "B", "recommended": True, "evidence": "accepted-b"},
            ],
            "recommended": {"code": "B"},
            "rejected": [{"evidence": secret}],
        },
        _set_relation_contract(),
    )

    assert [item.to_dict() for item in violations] == [
        {
            "path": "candidates",
            "keyword": "fieldRelation",
            "expected": "exactly_one_recommended_candidate",
            "actual": "count_where_equals_violated",
        },
        {
            "path": "candidates",
            "keyword": "fieldRelation",
            "expected": "accepted_and_rejected_evidence_are_disjoint",
            "actual": "disjoint_fields_violated",
        },
    ]
    assert secret not in repr(violations)


def test_set_relation_definition_rejects_untyped_item_paths() -> None:
    contract = _set_relation_contract()
    contract["field_relations"][1]["must"][0]["item_path"] = "missing"
    contract["field_relations"][2]["must"][0]["other_path"] = "recommended"

    errors = validate_field_relations_definition(contract)

    assert any("item_path must resolve inside array items" in error for error in errors)
    assert any("other_path must resolve to an object array" in error for error in errors)


def _evidence_binding_contract() -> dict:
    return {
        "required_fields": ["findings"],
        "field_types": {"findings": "array"},
        "field_schemas": {
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "evidence_text": {"type": "string"},
                        "char_span": {
                            "type": "array",
                            "items": {"type": "integer", "minimum": 0},
                            "minItems": 2,
                            "maxItems": 2,
                            "x-order": "nondecreasing",
                        },
                    },
                    "required": ["evidence_text", "char_span"],
                    "additionalProperties": False,
                },
            }
        },
        "evidence_bindings": [{
            "id": "finding_evidence_matches_input",
            "for_each": "findings",
            "text_path": "evidence_text",
            "span_path": "char_span",
        }],
    }


def test_evidence_binding_accepts_exact_source_slice() -> None:
    contract = _evidence_binding_contract()

    assert validate_evidence_bindings_definition(contract) == []
    assert validate_evidence_bindings(
        {"findings": [{"evidence_text": "肺炎", "char_span": [3, 5]}]},
        contract,
        "诊断：肺炎。",
    ) == []


def test_evidence_binding_rejects_mismatch_and_bounds_without_phi() -> None:
    secret = "patient-secret-evidence-marker"
    contract = _evidence_binding_contract()

    mismatch = validate_evidence_bindings(
        {"findings": [{"evidence_text": secret, "char_span": [3, 5]}]},
        contract,
        "诊断：肺炎。",
    )
    bounds = validate_evidence_bindings(
        {"findings": [{"evidence_text": secret, "char_span": [3, 500]}]},
        contract,
        "诊断：肺炎。",
    )

    assert [item.to_dict() for item in mismatch] == [{
        "path": "findings[].evidence_text",
        "keyword": "evidenceBinding",
        "expected": "finding_evidence_matches_input",
        "actual": "source_text_mismatch",
    }]
    assert [item.to_dict() for item in bounds] == [{
        "path": "findings[].char_span",
        "keyword": "evidenceBinding",
        "expected": "finding_evidence_matches_input",
        "actual": "out_of_source_bounds",
    }]
    assert secret not in repr(mismatch + bounds)


def test_evidence_binding_definition_rejects_untyped_paths() -> None:
    contract = _evidence_binding_contract()
    contract["evidence_bindings"][0]["text_path"] = "char_span"
    contract["evidence_bindings"][0]["span_path"] = "evidence_text"

    errors = validate_evidence_bindings_definition(contract)

    assert any("text_path must resolve to an item string" in error for error in errors)
    assert any("span_path must resolve to a two-integer item array" in error for error in errors)


def _document_evidence_binding_contract(*, with_version: bool = False) -> dict:
    properties = {
        "quote": {"type": "string"},
        "char_start": {"type": "integer"},
        "char_end": {"type": "integer"},
        "document_id": {"type": "string"},
    }
    required = list(properties)
    binding = {
        "id": "document_evidence_matches_source",
        "for_each": "findings",
        "text_path": "evidence.quote",
        "start_path": "evidence.char_start",
        "end_path": "evidence.char_end",
        "document_id_path": "evidence.document_id",
    }
    if with_version:
        properties["document_version"] = {"type": "string"}
        required.append("document_version")
        binding["document_version_path"] = "evidence.document_version"
    return {
        "required_fields": ["findings"],
        "field_types": {"findings": "array"},
        "field_schemas": {
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "evidence": {
                            "type": "object",
                            "properties": properties,
                            "required": required,
                            "additionalProperties": False,
                        }
                    },
                    "required": ["evidence"],
                    "additionalProperties": False,
                },
            }
        },
        "evidence_bindings": [binding],
    }


def test_multidocument_evidence_binding_uses_id_version_and_nfkc_text() -> None:
    contract = _document_evidence_binding_contract(with_version=True)
    documents, errors = prepare_source_documents([{
        "document_id": "admission",
        "document_version": "v2",
        "normalization": "NFKC",
        "text": "ＡＢ肺炎",
    }])

    assert errors == []
    assert documents[0].text == "AB肺炎"
    assert len(documents[0].content_sha256) == 64
    assert validate_evidence_bindings_definition(contract) == []
    assert validate_evidence_bindings(
        {"findings": [{"evidence": {
            "quote": "AB",
            "char_start": 0,
            "char_end": 2,
            "document_id": "admission",
            "document_version": "v2",
        }}]},
        contract,
        source_documents=documents,
    ) == []


def test_multidocument_binding_rejects_wrong_version_and_ambiguous_id_phi_safely() -> None:
    secret = "patient-secret-evidence-marker"
    versioned_contract = _document_evidence_binding_contract(with_version=True)
    documents = [
        {"document_id": "admission", "document_version": "v1", "text": secret},
        {"document_id": "admission", "document_version": "v2", "text": secret},
    ]
    wrong_version = validate_evidence_bindings(
        {"findings": [{"evidence": {
            "quote": secret,
            "char_start": 0,
            "char_end": len(secret),
            "document_id": "admission",
            "document_version": "v3",
        }}]},
        versioned_contract,
        source_documents=documents,
    )
    unversioned_contract = _document_evidence_binding_contract()
    ambiguous = validate_evidence_bindings(
        {"findings": [{"evidence": {
            "quote": secret,
            "char_start": 0,
            "char_end": len(secret),
            "document_id": "admission",
        }}]},
        unversioned_contract,
        source_documents=documents,
    )

    assert wrong_version[0].actual == "document_version_not_found"
    assert ambiguous[0].actual == "document_version_ambiguous"
    assert secret not in repr(wrong_version + ambiguous)


def _cross_agent_contract() -> dict:
    return {
        "required_fields": ["recommended", "candidates"],
        "field_types": {"recommended": "object", "candidates": "array"},
        "field_schemas": {
            "recommended": {
                "type": "object",
                "properties": {"code": {"type": "string"}},
                "required": ["code"],
                "additionalProperties": False,
            },
            "candidates": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"code": {"type": "string"}},
                    "required": ["code"],
                    "additionalProperties": False,
                },
            },
        },
        "cross_agent_relations": [{
            "id": "principal_matches_extracted_diagnosis",
            "local_path": "recommended.code",
            "upstream_agent_id": "diagnosis-extractor",
            "upstream_path": "diagnoses",
            "upstream_item_path": "code",
            "operator": "scalar_in_upstream_items",
            "normalization": "medical_code",
            "required": True,
        }],
    }


def test_cross_agent_relation_accepts_match_and_rejects_conflict_phi_safely() -> None:
    contract = _cross_agent_contract()
    upstream = [{
        "agent_id": "diagnosis-extractor",
        "result": {"diagnoses": [{"code": "ｉ２１．０"}]},
    }]

    assert validate_cross_agent_relations_definition(contract) == []
    assert validate_cross_agent_relations(
        {"recommended": {"code": "I21.0"}, "candidates": []},
        contract,
        upstream,
    ) == []
    conflict = validate_cross_agent_relations(
        {"recommended": {"code": "patient-secret-code"}, "candidates": []},
        contract,
        upstream,
    )
    assert [item.to_dict() for item in conflict] == [{
        "path": "recommended.code",
        "keyword": "crossAgentRelation",
        "expected": "principal_matches_extracted_diagnosis",
        "actual": "scalar_in_upstream_items_violated",
    }]
    assert "patient-secret-code" not in repr(conflict)


def test_cross_agent_required_upstream_is_fail_closed() -> None:
    violations = validate_cross_agent_relations(
        {"recommended": {"code": "I21.0"}, "candidates": []},
        _cross_agent_contract(),
        [],
    )

    assert violations[0].actual == "required_upstream_missing"


def test_cross_agent_equals_normalizes_both_sides() -> None:
    contract = _cross_agent_contract()
    relation = contract["cross_agent_relations"][0]
    relation.update({
        "operator": "equals_upstream",
        "upstream_path": "primary_code",
    })
    assert validate_cross_agent_relations(
        {"recommended": {"code": " i21.0 "}, "candidates": []},
        contract,
        [{
            "agent_id": "diagnosis-extractor",
            "result": {"primary_code": "Ｉ２１．０"},
        }],
    ) == []


def test_cross_agent_subset_can_union_scalar_and_collection_sources() -> None:
    contract = _cross_agent_contract()
    contract["cross_agent_relations"] = [{
        "id": "validated_codes_match_coding_result",
        "local_path": "candidates",
        "local_item_path": "code",
        "upstream_agent_id": "medical-coding-agent",
        "upstream_sources": [
            {"path": "code_assignment.primary_diagnosis.code"},
            {
                "path": "code_assignment.secondary_diagnoses",
                "item_path": "code",
            },
            {"path": "code_assignment.procedures", "item_path": "code"},
        ],
        "operator": "local_items_subset_upstream_values",
        "normalization": "medical_code",
        "required": False,
    }]
    upstream = [{
        "agent_id": "medical-coding-agent",
        "result": {
            "code_assignment": {
                "primary_diagnosis": {"code": "Ｉ２１．０"},
                "secondary_diagnoses": [{"code": "E11.9"}],
                "procedures": [{"code": "36.01"}],
            },
        },
    }]

    assert validate_cross_agent_relations_definition(contract) == []
    assert validate_cross_agent_relations(
        {
            "recommended": {"code": "I21.0"},
            "candidates": [
                {"code": "i21.0"}, {"code": " E11.9 "}, {"code": "36.01"},
            ],
        },
        contract,
        upstream,
    ) == []
    conflict = validate_cross_agent_relations(
        {
            "recommended": {"code": "I21.0"},
            "candidates": [{"code": "J18.9"}],
        },
        contract,
        upstream,
    )
    assert conflict[0].actual == "local_items_subset_upstream_values_violated"


def test_cross_agent_subset_allows_empty_local_only_when_declared() -> None:
    contract = _cross_agent_contract()
    relation = contract["cross_agent_relations"][0]
    relation.update({
        "local_path": "candidates",
        "local_item_path": "code",
        "operator": "local_items_subset_upstream_items",
        "allow_empty_local": True,
    })
    upstream = [{
        "agent_id": "diagnosis-extractor",
        "result": {"diagnoses": [{"code": "I21.0"}]},
    }]

    assert validate_cross_agent_relations_definition(contract) == []
    assert validate_cross_agent_relations(
        {"recommended": {"code": "I21.0"}, "candidates": []},
        contract,
        upstream,
    ) == []
