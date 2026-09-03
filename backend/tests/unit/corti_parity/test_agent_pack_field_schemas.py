from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "corti_parity" / "sync_agent_pack_field_schemas.py"
SPEC = importlib.util.spec_from_file_location("agent_pack_field_schemas", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_inference_closes_nested_objects_and_intersects_required_fields() -> None:
    schema = MODULE._infer(
        [
            [{"name": "a", "confidence": 1, "note": "x"}],
            [{"name": "b", "confidence": 0.5}],
        ],
        agent="example",
        path="items",
    )

    assert schema["type"] == "array"
    assert schema["items"]["additionalProperties"] is False
    assert schema["items"]["required"] == ["confidence", "name"]
    assert schema["items"]["properties"]["confidence"]["type"] == "number"


def test_empty_array_requires_explicit_reviewed_item_schema() -> None:
    with pytest.raises(ValueError, match="needs an explicit empty-array item schema"):
        MODULE._infer([[]], agent="unknown-agent", path="unknown_items")


def test_every_visible_pack_has_a_derivable_recursive_schema() -> None:
    agents_dir = Path(__file__).resolve().parents[3] / "official_agents"
    report = MODULE.sync_field_schemas(agents_dir, write=False)
    assert report == {"visible_agents": 26, "changed_agents": [], "write": False}


def test_reviewed_value_constraints_cover_high_risk_agent_fields() -> None:
    agents_dir = Path(__file__).resolve().parents[3] / "official_agents"

    evidence = json.loads(
        (agents_dir / "evidence_extractor" / "agent_pack.json").read_text(encoding="utf-8")
    )["output_contract"]["field_schemas"]
    mention = evidence["located_mentions"]["items"]["properties"]
    assert mention["char_span"] == {
        "type": "array",
        "items": {"type": "integer", "minimum": 0},
        "maxItems": 2,
        "minItems": 2,
        "x-order": "nondecreasing",
    }
    assert mention["clinical_support_assessed"]["const"] is False
    assert mention["match_type"]["enum"] == [
        "exact_code_literal", "exact_catalog_term",
    ]
    assert evidence["match_basis"]["const"] == (
        "EXACT_CATALOG_TERM_OR_CODE_LITERAL_ONLY"
    )
    assert evidence["manual_review_required"]["const"] is True
    assert evidence["uncoded_findings"]["maxItems"] == 0
    result_fields = evidence["code_results"]["items"]["properties"]
    assert result_fields["clinical_support_assessed"]["const"] is False
    assert result_fields["mention_count"]["maximum"] == 5

    procedure = json.loads(
        (agents_dir / "procedure-extractor" / "agent_pack.json").read_text(encoding="utf-8")
    )["output_contract"]["field_schemas"]
    assert procedure["manual_review_required"]["const"] is True
    assert procedure["procedures"]["items"]["properties"]["status"]["enum"] == [
        "performed", "planned", "historical", "cancelled", "negated", "unknown",
    ]
    non_billable = procedure["non_billable_mentions"]["items"]["properties"]
    assert "enum" not in non_billable["text"]
    assert "enum" not in non_billable["evidence_text"]
    assert non_billable["status"]["enum"] == [
        "performed", "planned", "historical", "cancelled", "negated", "unknown",
    ]

    diagnosis = json.loads(
        (agents_dir / "diagnosis-extractor" / "agent_pack.json").read_text(encoding="utf-8")
    )["output_contract"]["field_schemas"]
    assert diagnosis["status"]["enum"] == ["PASS", "WARNING", "REQUIRES_REVIEW"]
    assert diagnosis["diagnoses"]["items"]["properties"]["confidence"]["enum"] == [
        "high", "medium", "low",
    ]

    surgical = json.loads(
        (agents_dir / "surgical_registry" / "agent_pack.json").read_text(
            encoding="utf-8"
        )
    )["output_contract"]["field_schemas"]["evidence_spans"]
    assert surgical["required"] == []
    assert set(surgical["properties"]) == {
        "procedure",
        "indications",
        "comorbidities",
        "operative_details",
        "anesthesia",
        "outcomes",
        "complications",
    }


def test_reviewed_cross_field_relations_cover_clinical_consistency() -> None:
    agents_dir = Path(__file__).resolve().parents[3] / "official_agents"

    procedure = json.loads(
        (agents_dir / "procedure-extractor" / "agent_pack.json").read_text(encoding="utf-8")
    )["output_contract"]["field_relations"]
    assert procedure[0] == {
        "id": "procedure_count_matches_items",
        "when": [{"path": "procedures", "operator": "present"}],
        "must": [{
            "path": "procedures",
            "operator": "length_equals",
            "other_path": "total_count",
        }],
    }

    medical_coding = json.loads(
        (agents_dir / "medical_coding" / "agent_pack.json").read_text(encoding="utf-8")
    )["output_contract"]["field_relations"]
    assert medical_coding == MODULE.FIELD_RELATION_OVERRIDES["medical_coding"]


def test_multidocument_bindings_and_cross_agent_relations_are_pack_mastered() -> None:
    agents_dir = Path(__file__).resolve().parents[3] / "official_agents"

    for agent in (
        "clinical-documentation-improvement-agent",
        "medical_coding",
    ):
        contract = json.loads(
            (agents_dir / agent / "agent_pack.json").read_text(encoding="utf-8")
        )["output_contract"]
        assert contract["evidence_bindings"] == MODULE.EVIDENCE_BINDING_OVERRIDES[agent]
        assert any(
            "document_id_path" in binding
            for binding in contract["evidence_bindings"]
        )

    for agent in (
        "evidence_extractor",
        "medical_coding",
        "principal_diagnosis_review",
    ):
        contract = json.loads(
            (agents_dir / agent / "agent_pack.json").read_text(encoding="utf-8")
        )["output_contract"]
        assert contract["cross_agent_relations"] == (
            MODULE.CROSS_AGENT_RELATION_OVERRIDES[agent]
        )
        assert contract["cross_agent_relations"][0]["normalization"] == "medical_code"
