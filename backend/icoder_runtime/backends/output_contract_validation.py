"""Small, PHI-safe validators for Agent Pack public output contracts.

The Pack owns the public top-level field names and their JSON-compatible
types and an intentionally small recursive JSON-Schema subset. Validation
deliberately reports declared paths and type/keyword metadata only, never the
rejected value or an undeclared property name, so a malformed provider
response cannot leak chart content through logs or audit records.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
import hashlib
import json
import math
import re
import unicodedata
from typing import Any


SUPPORTED_FIELD_TYPES = frozenset(
    {"string", "boolean", "integer", "number", "object", "array"}
)
SUPPORTED_SCHEMA_KEYWORDS = frozenset({
    "type", "properties", "required", "additionalProperties", "items",
    "enum", "const", "minimum", "maximum", "minLength", "maxLength",
    "pattern", "minItems", "maxItems", "uniqueItems", "x-order",
})
SUPPORTED_RELATION_OPERATORS = frozenset({
    "equals", "not_equals", "present", "absent", "empty", "non_empty",
    "equals_path", "not_equals_path", "length_equals", "in", "not_in",
    "gt", "gte", "lt", "lte",
    "count_where_equals", "contains_field_equals_path", "disjoint_fields",
})
_RELATION_ID = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
_RELATION_PATH = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")
_MISSING = object()
SUPPORTED_DOCUMENT_NORMALIZATIONS = frozenset({"none", "NFC", "NFKC"})
SUPPORTED_CROSS_AGENT_OPERATORS = frozenset({
    "equals_upstream",
    "scalar_in_upstream_items",
    "local_items_subset_upstream_items",
    "local_items_overlap_upstream_items",
    "local_items_subset_upstream_values",
})


@dataclass(frozen=True)
class FieldTypeViolation:
    field: str
    expected: str
    actual: str

    def to_dict(self) -> dict[str, str]:
        return {
            "field": self.field,
            "expected": self.expected,
            "actual": self.actual,
        }


@dataclass(frozen=True)
class FieldSchemaViolation:
    path: str
    keyword: str
    expected: str
    actual: str

    def to_dict(self) -> dict[str, str]:
        return {
            "path": self.path,
            "keyword": self.keyword,
            "expected": self.expected,
            "actual": self.actual,
        }


@dataclass(frozen=True)
class PreparedSourceDocument:
    """A de-identified, normalized document used for evidence validation."""

    document_id: str
    text: str
    document_version: str = ""
    document_type: str = ""
    normalization: str = "none"
    content_sha256: str = ""

    def to_runtime_dict(self) -> dict[str, str]:
        return {
            "document_id": self.document_id,
            "document_version": self.document_version,
            "document_type": self.document_type,
            "normalization": self.normalization,
            "text": self.text,
            "content_sha256": self.content_sha256,
        }


def json_type_name(value: Any) -> str:
    """Return the JSON type name while keeping bool distinct from int."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number" if math.isfinite(value) else "non_finite_number"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    return type(value).__name__


def value_matches_type(value: Any, expected: str) -> bool:
    """Validate the supported top-level JSON type vocabulary."""
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return (
            isinstance(value, int) and not isinstance(value, bool)
        ) or (
            isinstance(value, float) and math.isfinite(value)
        )
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    return False


def declared_field_types(output_contract: Any) -> dict[str, str]:
    if not isinstance(output_contract, dict):
        return {}
    raw = output_contract.get("field_types")
    if not isinstance(raw, dict):
        return {}
    return {
        field: expected
        for field, expected in raw.items()
        if isinstance(field, str) and isinstance(expected, str)
    }


def declared_optional_fields(output_contract: Any) -> list[str]:
    if not isinstance(output_contract, dict):
        return []
    raw = output_contract.get("optional_fields")
    if not isinstance(raw, list):
        return []
    return [field for field in raw if isinstance(field, str)]


def declared_field_schemas(output_contract: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(output_contract, dict):
        return {}
    raw = output_contract.get("field_schemas")
    if not isinstance(raw, dict):
        return {}
    return {
        field: schema
        for field, schema in raw.items()
        if isinstance(field, str) and isinstance(schema, dict)
    }


def apply_declared_constants(
    payload: Any,
    output_contract: Any,
) -> dict[str, Any]:
    """Project implementation-owned ``const`` fields authoritatively.

    A model may omit an optional governance marker or attempt to contradict
    it.  The runtime, rather than the model, owns declared constants such as
    mandatory review and non-billing authority.  Undeclared payload fields are
    preserved here so the caller can still reject them separately.
    """
    normalized = dict(payload) if isinstance(payload, dict) else {}
    declared = set(declared_contract_fields(output_contract))
    for field, schema in declared_field_schemas(output_contract).items():
        if field in declared and "const" in schema:
            normalized[field] = copy.deepcopy(schema["const"])
    return normalized


def declared_field_relations(output_contract: Any) -> list[dict[str, Any]]:
    """Return only relation objects; definition validation rejects mixed lists."""
    if not isinstance(output_contract, dict):
        return []
    raw = output_contract.get("field_relations")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def declared_evidence_bindings(output_contract: Any) -> list[dict[str, Any]]:
    """Return declared source-text bindings for evidence-bearing array items."""
    if not isinstance(output_contract, dict):
        return []
    raw = output_contract.get("evidence_bindings")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def declared_cross_agent_relations(output_contract: Any) -> list[dict[str, Any]]:
    """Return declared local/upstream result consistency checks."""
    if not isinstance(output_contract, dict):
        return []
    raw = output_contract.get("cross_agent_relations")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def prepare_source_documents(
    source_documents: Any,
    *,
    fallback_text: Any = None,
    fallback_document_id: str = "input",
    require_unique_document_ids: bool = False,
) -> tuple[list[PreparedSourceDocument], list[FieldSchemaViolation]]:
    """Validate and normalize a bounded, PHI-safe source-document set.

    Callers must pass already de-identified strings.  Only fixed schema paths,
    JSON type names and abstract failure reasons are returned in violations.
    The normalized content hash lets audit consumers bind an output to an
    immutable document version without persisting the document text here.
    """
    raw_documents = source_documents
    if raw_documents is None:
        raw_documents = []
    violations: list[FieldSchemaViolation] = []

    def add(path: str, expected: str, actual: str) -> None:
        item = FieldSchemaViolation(
            path=path,
            keyword="sourceDocument",
            expected=expected,
            actual=actual,
        )
        if item not in violations:
            violations.append(item)

    if not isinstance(raw_documents, list):
        add("documents", "array", json_type_name(raw_documents))
        return [], violations
    if len(raw_documents) > 32:
        add("documents", "at_most_32", "too_many_documents")
        return [], violations

    prepared: list[PreparedSourceDocument] = []
    identities: set[tuple[str, str]] = set()
    document_ids: set[str] = set()
    total_chars = 0
    for item in raw_documents:
        if isinstance(item, PreparedSourceDocument):
            item = item.to_runtime_dict()
        if not isinstance(item, dict):
            add("documents[]", "object", json_type_name(item))
            continue
        document_id = item.get("document_id")
        text = item.get("text")
        document_version = item.get("document_version", "")
        document_type = item.get("document_type", "")
        normalization = item.get("normalization", "NFC")
        if not isinstance(document_id, str) or not document_id.strip():
            add("documents[].document_id", "non_empty_string", "invalid_identifier")
            continue
        if (
            len(document_id) > 128
            or any(ord(char) < 32 for char in document_id)
        ):
            add("documents[].document_id", "bounded_identifier", "invalid_identifier")
            continue
        if not isinstance(text, str) or not text:
            add("documents[].text", "non_empty_string", json_type_name(text))
            continue
        if len(text) > 64_000:
            add("documents[].text", "at_most_64000_chars", "too_long")
            continue
        if not isinstance(document_version, str) or len(document_version) > 128:
            add("documents[].document_version", "bounded_string", json_type_name(document_version))
            continue
        if not isinstance(document_type, str) or len(document_type) > 128:
            add("documents[].document_type", "bounded_string", json_type_name(document_type))
            continue
        if not isinstance(normalization, str):
            add("documents[].normalization", "none_or_unicode_form", json_type_name(normalization))
            continue
        normalized_form = "none" if normalization.casefold() == "none" else normalization.upper()
        if normalized_form not in SUPPORTED_DOCUMENT_NORMALIZATIONS:
            add("documents[].normalization", "none_or_NFC_or_NFKC", "unsupported")
            continue
        identity = (document_id, document_version)
        if require_unique_document_ids and document_id in document_ids:
            add("documents[]", "unique_document_id", "duplicate_document_id")
            continue
        if identity in identities:
            add("documents[]", "unique_document_id_version", "duplicate_identity")
            continue
        identities.add(identity)
        document_ids.add(document_id)
        normalized_text = (
            text
            if normalized_form == "none"
            else unicodedata.normalize(normalized_form, text)
        )
        total_chars += len(normalized_text)
        if total_chars > 256_000:
            add("documents", "at_most_256000_chars", "total_too_long")
            return [], violations
        prepared.append(PreparedSourceDocument(
            document_id=document_id,
            document_version=document_version,
            document_type=document_type,
            normalization=normalized_form,
            text=normalized_text,
            content_sha256=hashlib.sha256(normalized_text.encode("utf-8")).hexdigest(),
        ))

    if not prepared and isinstance(fallback_text, str) and fallback_text:
        prepared.append(PreparedSourceDocument(
            document_id=fallback_document_id,
            text=fallback_text,
            content_sha256=hashlib.sha256(fallback_text.encode("utf-8")).hexdigest(),
        ))
    return prepared, violations


def _relation_path_schema(
    output_contract: dict[str, Any],
    relation_path: Any,
    *,
    scope_schema: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if not isinstance(relation_path, str) or not _RELATION_PATH.fullmatch(relation_path):
        return None
    parts = relation_path.split(".")
    if scope_schema is None:
        schema = declared_field_schemas(output_contract).get(parts[0])
        remaining = parts[1:]
    else:
        schema = scope_schema
        remaining = parts
    for part in remaining:
        if not isinstance(schema, dict) or schema.get("type") != "object":
            return None
        properties = schema.get("properties")
        if not isinstance(properties, dict):
            return None
        schema = properties.get(part)
    return schema if isinstance(schema, dict) else None


def validate_field_relations_definition(
    output_contract: Any,
    *,
    path: str = "output_contract.field_relations",
) -> list[str]:
    """Validate a bounded implication DSL for cross-field public invariants."""
    if not isinstance(output_contract, dict):
        return [f"{path} requires an output contract object"]
    raw = output_contract.get("field_relations")
    if raw is None:
        return []
    if not isinstance(raw, list) or not raw:
        return [f"{path} must be a non-empty array when present"]
    if len(raw) > 32:
        return [f"{path} must contain at most 32 relations"]

    errors: list[str] = []
    ids: set[str] = set()

    def validate_predicate(
        predicate: Any,
        predicate_path: str,
        scope_schema: dict[str, Any] | None,
        *,
        nested_where: bool = False,
    ) -> None:
        if not isinstance(predicate, dict):
            errors.append(f"{predicate_path} must be an object")
            return
        unknown = sorted(
            set(predicate)
            - {
                "path", "operator", "value", "other_path", "where",
                "item_path", "other_item_path",
            }
        )
        if unknown:
            errors.append(
                f"{predicate_path} contains unsupported keys: {', '.join(unknown)}"
            )
        relation_path = predicate.get("path")
        schema = _relation_path_schema(
            output_contract, relation_path, scope_schema=scope_schema
        )
        if schema is None:
            errors.append(f"{predicate_path}.path must resolve to a declared object field")
        operator = predicate.get("operator")
        if operator not in SUPPORTED_RELATION_OPERATORS:
            errors.append(f"{predicate_path}.operator is unsupported")
            return
        has_value = "value" in predicate
        has_other = "other_path" in predicate
        has_where = "where" in predicate
        has_item_path = "item_path" in predicate
        has_other_item_path = "other_item_path" in predicate
        set_operator = operator in {
            "count_where_equals", "contains_field_equals_path", "disjoint_fields",
        }
        if nested_where and set_operator:
            errors.append(f"{predicate_path}.{operator} cannot be nested inside where")
            return
        if not set_operator and (has_where or has_item_path or has_other_item_path):
            errors.append(f"{predicate_path}.{operator} does not accept set-operation keys")
            return
        if operator in {"equals", "not_equals", "gt", "gte", "lt", "lte"}:
            if not has_value or has_other:
                errors.append(f"{predicate_path}.{operator} requires value only")
            elif schema is not None and not value_matches_type(
                predicate.get("value"), str(schema.get("type"))
            ):
                errors.append(f"{predicate_path}.value must match the declared path type")
            elif operator in {"gt", "gte", "lt", "lte"} and (
                schema is not None and schema.get("type") not in {"integer", "number"}
            ):
                errors.append(f"{predicate_path}.{operator} requires a numeric path")
        elif operator in {"in", "not_in"}:
            values = predicate.get("value")
            if not has_value or has_other or not isinstance(values, list) or not values:
                errors.append(f"{predicate_path}.{operator} requires a non-empty value array")
            elif schema is not None:
                encoded = [
                    json.dumps(item, sort_keys=True, ensure_ascii=False) for item in values
                ]
                if len(set(encoded)) != len(encoded):
                    errors.append(f"{predicate_path}.value entries must be unique")
                if any(
                    not value_matches_type(item, str(schema.get("type")))
                    for item in values
                ):
                    errors.append(
                        f"{predicate_path}.value entries must match the declared path type"
                    )
        elif operator in {"equals_path", "not_equals_path", "length_equals"}:
            if has_value or not has_other:
                errors.append(f"{predicate_path}.{operator} requires other_path only")
                return
            other_schema = _relation_path_schema(
                output_contract,
                predicate.get("other_path"),
                scope_schema=scope_schema,
            )
            if other_schema is None:
                errors.append(
                    f"{predicate_path}.other_path must resolve to a declared object field"
                )
            elif schema is not None:
                if operator == "length_equals":
                    if schema.get("type") != "array" or other_schema.get("type") != "integer":
                        errors.append(
                            f"{predicate_path}.length_equals requires array and integer paths"
                        )
                elif schema.get("type") != other_schema.get("type"):
                    errors.append(f"{predicate_path}.{operator} paths must have matching types")
        elif set_operator:
            if scope_schema is not None:
                errors.append(f"{predicate_path}.{operator} is only supported at root scope")
            if schema is None or schema.get("type") != "array":
                errors.append(f"{predicate_path}.{operator} requires an object-array path")
                item_schema = None
            else:
                item_schema = schema.get("items")
                if not isinstance(item_schema, dict) or item_schema.get("type") != "object":
                    errors.append(f"{predicate_path}.{operator} requires an object-array path")
                    item_schema = None
            where = predicate.get("where")
            if has_where:
                if not isinstance(where, list) or not where or len(where) > 8:
                    errors.append(
                        f"{predicate_path}.where must contain between 1 and 8 predicates"
                    )
                elif item_schema is not None:
                    for index, child in enumerate(where):
                        validate_predicate(
                            child,
                            f"{predicate_path}.where[{index}]",
                            item_schema,
                            nested_where=True,
                        )
            if operator == "count_where_equals":
                if (
                    not has_where or has_other or has_item_path or has_other_item_path
                    or not isinstance(predicate.get("value"), int)
                    or isinstance(predicate.get("value"), bool)
                    or predicate["value"] < 0
                ):
                    errors.append(
                        f"{predicate_path}.count_where_equals requires where and a non-negative integer value"
                    )
            elif operator == "contains_field_equals_path":
                if has_value or not has_other or not has_item_path or has_other_item_path:
                    errors.append(
                        f"{predicate_path}.contains_field_equals_path requires item_path and other_path"
                    )
                item_field_schema = _relation_path_schema(
                    output_contract,
                    predicate.get("item_path"),
                    scope_schema=item_schema,
                ) if item_schema is not None else None
                other_schema = _relation_path_schema(
                    output_contract, predicate.get("other_path")
                )
                if item_field_schema is None:
                    errors.append(f"{predicate_path}.item_path must resolve inside array items")
                if other_schema is None:
                    errors.append(f"{predicate_path}.other_path must resolve to a declared field")
                if (
                    item_field_schema is not None and other_schema is not None
                    and item_field_schema.get("type") != other_schema.get("type")
                ):
                    errors.append(f"{predicate_path}.contains_field_equals_path types must match")
            else:
                if (
                    has_value or not has_other or not has_item_path
                    or not has_other_item_path or has_where
                ):
                    errors.append(
                        f"{predicate_path}.disjoint_fields requires two array paths and item paths"
                    )
                other_array = _relation_path_schema(
                    output_contract, predicate.get("other_path")
                )
                other_item_schema = (
                    other_array.get("items")
                    if isinstance(other_array, dict) and other_array.get("type") == "array"
                    else None
                )
                if not isinstance(other_item_schema, dict) or other_item_schema.get("type") != "object":
                    errors.append(f"{predicate_path}.other_path must resolve to an object array")
                    other_item_schema = None
                left_schema = _relation_path_schema(
                    output_contract,
                    predicate.get("item_path"),
                    scope_schema=item_schema,
                ) if item_schema is not None else None
                right_schema = _relation_path_schema(
                    output_contract,
                    predicate.get("other_item_path"),
                    scope_schema=other_item_schema,
                ) if other_item_schema is not None else None
                if left_schema is None:
                    errors.append(f"{predicate_path}.item_path must resolve inside array items")
                if right_schema is None:
                    errors.append(
                        f"{predicate_path}.other_item_path must resolve inside other array items"
                    )
                if (
                    left_schema is not None and right_schema is not None
                    and left_schema.get("type") != right_schema.get("type")
                ):
                    errors.append(f"{predicate_path}.disjoint_fields item types must match")
        elif has_value or has_other:
            errors.append(f"{predicate_path}.{operator} does not accept value or other_path")

    for index, relation in enumerate(raw):
        relation_path = f"{path}[{index}]"
        if not isinstance(relation, dict):
            errors.append(f"{relation_path} must be an object")
            continue
        unknown = sorted(set(relation) - {"id", "for_each", "when", "must"})
        if unknown:
            errors.append(f"{relation_path} contains unsupported keys: {', '.join(unknown)}")
        relation_id = relation.get("id")
        if not isinstance(relation_id, str) or not _RELATION_ID.fullmatch(relation_id):
            errors.append(f"{relation_path}.id must be a stable lowercase identifier")
        elif relation_id in ids:
            errors.append(f"{relation_path}.id must be unique")
        else:
            ids.add(relation_id)
        scope_schema = None
        for_each = relation.get("for_each")
        if for_each is not None:
            array_schema = _relation_path_schema(output_contract, for_each)
            if (
                array_schema is None
                or array_schema.get("type") != "array"
                or not isinstance(array_schema.get("items"), dict)
                or array_schema["items"].get("type") != "object"
            ):
                errors.append(
                    f"{relation_path}.for_each must resolve to an array of declared objects"
                )
            else:
                scope_schema = array_schema["items"]
        for group in ("when", "must"):
            predicates = relation.get(group)
            if not isinstance(predicates, list) or not predicates or len(predicates) > 8:
                errors.append(
                    f"{relation_path}.{group} must contain between 1 and 8 predicates"
                )
                continue
            for predicate_index, predicate in enumerate(predicates):
                validate_predicate(
                    predicate,
                    f"{relation_path}.{group}[{predicate_index}]",
                    scope_schema,
                )
    return errors


def validate_evidence_bindings_definition(
    output_contract: Any,
    *,
    path: str = "output_contract.evidence_bindings",
) -> list[str]:
    """Validate exact quote/span bindings for single or versioned documents."""
    if not isinstance(output_contract, dict):
        return [f"{path} requires an output contract object"]
    raw = output_contract.get("evidence_bindings")
    if raw is None:
        return []
    if not isinstance(raw, list) or not raw:
        return [f"{path} must be a non-empty array when present"]
    if len(raw) > 32:
        return [f"{path} must contain at most 32 bindings"]
    errors: list[str] = []
    ids: set[str] = set()
    for index, binding in enumerate(raw):
        binding_path = f"{path}[{index}]"
        if not isinstance(binding, dict):
            errors.append(f"{binding_path} must be an object")
            continue
        unknown = sorted(set(binding) - {
            "id", "for_each", "text_path", "span_path", "start_path",
            "end_path", "document_id_path", "document_version_path",
        })
        if unknown:
            errors.append(
                f"{binding_path} contains unsupported keys: {', '.join(unknown)}"
            )
        binding_id = binding.get("id")
        if not isinstance(binding_id, str) or not _RELATION_ID.fullmatch(binding_id):
            errors.append(f"{binding_path}.id must be a stable lowercase identifier")
        elif binding_id in ids:
            errors.append(f"{binding_path}.id must be unique")
        else:
            ids.add(binding_id)
        array_schema = _relation_path_schema(output_contract, binding.get("for_each"))
        item_schema = (
            array_schema.get("items")
            if isinstance(array_schema, dict) and array_schema.get("type") == "array"
            else None
        )
        if not isinstance(item_schema, dict) or item_schema.get("type") != "object":
            errors.append(
                f"{binding_path}.for_each must resolve to an array of declared objects"
            )
            item_schema = None
        text_schema = _relation_path_schema(
            output_contract,
            binding.get("text_path"),
            scope_schema=item_schema,
        ) if item_schema is not None else None
        if text_schema is None or text_schema.get("type") != "string":
            errors.append(f"{binding_path}.text_path must resolve to an item string")
        has_span = "span_path" in binding
        has_start = "start_path" in binding
        has_end = "end_path" in binding
        if has_span == (has_start or has_end):
            errors.append(
                f"{binding_path} must declare span_path or start_path/end_path exclusively"
            )
        if has_span:
            span_schema = _relation_path_schema(
                output_contract,
                binding.get("span_path"),
                scope_schema=item_schema,
            ) if item_schema is not None else None
            span_items = span_schema.get("items") if isinstance(span_schema, dict) else None
            if (
                not isinstance(span_schema, dict)
                or span_schema.get("type") != "array"
                or not isinstance(span_items, dict)
                or span_items.get("type") != "integer"
                or span_schema.get("minItems") != 2
                or span_schema.get("maxItems") != 2
            ):
                errors.append(
                    f"{binding_path}.span_path must resolve to a two-integer item array"
                )
        else:
            if not (has_start and has_end):
                errors.append(f"{binding_path}.start_path and end_path must be paired")
            for key in ("start_path", "end_path"):
                schema = _relation_path_schema(
                    output_contract,
                    binding.get(key),
                    scope_schema=item_schema,
                ) if item_schema is not None else None
                if schema is None or schema.get("type") != "integer":
                    errors.append(f"{binding_path}.{key} must resolve to an item integer")
        document_id_path = binding.get("document_id_path")
        if document_id_path is not None:
            schema = _relation_path_schema(
                output_contract,
                document_id_path,
                scope_schema=item_schema,
            ) if item_schema is not None else None
            if schema is None or schema.get("type") != "string":
                errors.append(
                    f"{binding_path}.document_id_path must resolve to an item string"
                )
        document_version_path = binding.get("document_version_path")
        if document_version_path is not None:
            if document_id_path is None:
                errors.append(
                    f"{binding_path}.document_version_path requires document_id_path"
                )
            schema = _relation_path_schema(
                output_contract,
                document_version_path,
                scope_schema=item_schema,
            ) if item_schema is not None else None
            if schema is None or schema.get("type") != "string":
                errors.append(
                    f"{binding_path}.document_version_path must resolve to an item string"
                )
    return errors


def validate_cross_agent_relations_definition(
    output_contract: Any,
    *,
    path: str = "output_contract.cross_agent_relations",
) -> list[str]:
    """Validate a bounded PHI-safe local/upstream result relation DSL."""
    if not isinstance(output_contract, dict):
        return [f"{path} requires an output contract object"]
    raw = output_contract.get("cross_agent_relations")
    if raw is None:
        return []
    if not isinstance(raw, list) or not raw:
        return [f"{path} must be a non-empty array when present"]
    if len(raw) > 16:
        return [f"{path} must contain at most 16 relations"]
    errors: list[str] = []
    ids: set[str] = set()
    allowed = {
        "id", "local_path", "local_item_path", "upstream_agent_id",
        "upstream_path", "upstream_item_path", "operator", "required",
        "normalization", "upstream_sources", "allow_empty_local",
    }
    for index, relation in enumerate(raw):
        relation_path = f"{path}[{index}]"
        if not isinstance(relation, dict):
            errors.append(f"{relation_path} must be an object")
            continue
        unknown = sorted(set(relation) - allowed)
        if unknown:
            errors.append(
                f"{relation_path} contains unsupported keys: {', '.join(unknown)}"
            )
        relation_id = relation.get("id")
        if not isinstance(relation_id, str) or not _RELATION_ID.fullmatch(relation_id):
            errors.append(f"{relation_path}.id must be a stable lowercase identifier")
        elif relation_id in ids:
            errors.append(f"{relation_path}.id must be unique")
        else:
            ids.add(relation_id)
        local_path = relation.get("local_path")
        local_schema = _relation_path_schema(output_contract, local_path)
        if local_schema is None:
            errors.append(f"{relation_path}.local_path must resolve to a declared field")
        upstream_agent_id = relation.get("upstream_agent_id")
        if (
            not isinstance(upstream_agent_id, str)
            or not _RELATION_ID.fullmatch(upstream_agent_id.replace("-", "_"))
        ):
            errors.append(f"{relation_path}.upstream_agent_id must be a stable agent id")
        operator = relation.get("operator")
        if operator not in SUPPORTED_CROSS_AGENT_OPERATORS:
            errors.append(f"{relation_path}.operator is unsupported")
            continue
        if operator == "local_items_subset_upstream_values":
            if "upstream_path" in relation or "upstream_item_path" in relation:
                errors.append(
                    f"{relation_path}.{operator} uses upstream_sources instead of "
                    "upstream_path/upstream_item_path"
                )
            sources = relation.get("upstream_sources")
            if not isinstance(sources, list) or not 1 <= len(sources) <= 8:
                errors.append(
                    f"{relation_path}.upstream_sources must contain 1 to 8 sources"
                )
            else:
                for source_index, source in enumerate(sources):
                    source_path = f"{relation_path}.upstream_sources[{source_index}]"
                    if not isinstance(source, dict):
                        errors.append(f"{source_path} must be an object")
                        continue
                    unknown_source_keys = sorted(set(source) - {"path", "item_path"})
                    if unknown_source_keys:
                        errors.append(
                            f"{source_path} contains unsupported keys: "
                            f"{', '.join(unknown_source_keys)}"
                        )
                    value = source.get("path")
                    if not isinstance(value, str) or not _RELATION_PATH.fullmatch(value):
                        errors.append(f"{source_path}.path must be a declared-style path")
                    item_path = source.get("item_path")
                    if item_path is not None and (
                        not isinstance(item_path, str)
                        or not _RELATION_PATH.fullmatch(item_path)
                    ):
                        errors.append(
                            f"{source_path}.item_path must be a declared-style path"
                        )
        else:
            if "upstream_sources" in relation:
                errors.append(
                    f"{relation_path}.{operator} does not accept upstream_sources"
                )
            for key in ("upstream_path", "upstream_item_path"):
                value = relation.get(key)
                if not isinstance(value, str) or not _RELATION_PATH.fullmatch(value):
                    errors.append(f"{relation_path}.{key} must be a declared-style path")
        required = relation.get("required", False)
        if not isinstance(required, bool):
            errors.append(f"{relation_path}.required must be boolean")
        allow_empty_local = relation.get("allow_empty_local", False)
        if not isinstance(allow_empty_local, bool):
            errors.append(f"{relation_path}.allow_empty_local must be boolean")
        if relation.get("normalization", "none") not in {"none", "medical_code"}:
            errors.append(f"{relation_path}.normalization is unsupported")
        local_item_path = relation.get("local_item_path")
        if operator.startswith("local_items_"):
            if not isinstance(local_schema, dict) or local_schema.get("type") != "array":
                errors.append(f"{relation_path}.{operator} requires an array local_path")
                local_item_schema = None
            else:
                local_item_schema = local_schema.get("items")
            item_schema = _relation_path_schema(
                output_contract,
                local_item_path,
                scope_schema=local_item_schema if isinstance(local_item_schema, dict) else None,
            ) if isinstance(local_item_schema, dict) else None
            if item_schema is None:
                errors.append(
                    f"{relation_path}.local_item_path must resolve inside local array items"
                )
        elif local_item_path is not None:
            errors.append(f"{relation_path}.{operator} does not accept local_item_path")
    return errors


def declared_contract_fields(output_contract: Any) -> list[str]:
    if not isinstance(output_contract, dict):
        return []
    required = output_contract.get("required_fields")
    required_fields = (
        [field for field in required if isinstance(field, str)]
        if isinstance(required, list) else []
    )
    return required_fields + [
        field for field in declared_optional_fields(output_contract)
        if field not in required_fields
    ]


def validate_required_field_types(
    payload: Any,
    output_contract: Any,
) -> list[FieldTypeViolation]:
    """Return violations for all present declared fields; missing is separate."""
    if not isinstance(payload, dict) or not isinstance(output_contract, dict):
        return []
    declared = declared_contract_fields(output_contract)
    types = declared_field_types(output_contract)
    violations: list[FieldTypeViolation] = []
    for field in declared:
        if not isinstance(field, str) or field not in payload:
            continue
        expected = types.get(field)
        if expected and not value_matches_type(payload[field], expected):
            violations.append(
                FieldTypeViolation(
                    field=field,
                    expected=expected,
                    actual=json_type_name(payload[field]),
                )
            )
    return violations


def validate_field_schema_definition(
    schema: Any,
    *,
    path: str,
    expected_root_type: str | None = None,
    _depth: int = 0,
) -> list[str]:
    """Validate the supported recursive schema subset used by first-party Packs."""
    if _depth > 8:
        return [f"{path} exceeds the maximum schema depth"]
    if not isinstance(schema, dict):
        return [f"{path} must be an object"]
    unknown_keywords = sorted(set(schema) - SUPPORTED_SCHEMA_KEYWORDS)
    if unknown_keywords:
        return [f"{path} contains unsupported keywords: {', '.join(unknown_keywords)}"]
    expected = schema.get("type")
    errors: list[str] = []
    if expected not in SUPPORTED_FIELD_TYPES:
        return [f"{path}.type must be a supported JSON type"]
    if expected_root_type and expected != expected_root_type:
        errors.append(
            f"{path}.type must match field_types ({expected_root_type})"
        )

    if "enum" in schema:
        enum = schema.get("enum")
        if not isinstance(enum, list) or not enum:
            errors.append(f"{path}.enum must be a non-empty array")
        else:
            encoded = [json.dumps(item, sort_keys=True, ensure_ascii=False) for item in enum]
            if len(set(encoded)) != len(encoded):
                errors.append(f"{path}.enum values must be unique")
            if any(not value_matches_type(item, str(expected)) for item in enum):
                errors.append(f"{path}.enum values must match type {expected}")
    if "const" in schema and not value_matches_type(schema.get("const"), str(expected)):
        errors.append(f"{path}.const must match type {expected}")

    numeric_keys = [key for key in ("minimum", "maximum") if key in schema]
    if numeric_keys and expected not in {"integer", "number"}:
        errors.append(f"{path} numeric bounds require integer or number type")
    for key in numeric_keys:
        value = schema.get(key)
        if not value_matches_type(value, "number"):
            errors.append(f"{path}.{key} must be a finite number")
    if (
        value_matches_type(schema.get("minimum"), "number")
        and value_matches_type(schema.get("maximum"), "number")
        and schema["minimum"] > schema["maximum"]
    ):
        errors.append(f"{path}.minimum must not exceed maximum")

    string_keys = [key for key in ("minLength", "maxLength") if key in schema]
    if (string_keys or "pattern" in schema) and expected != "string":
        errors.append(f"{path} string constraints require string type")
    for key in string_keys:
        value = schema.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            errors.append(f"{path}.{key} must be a non-negative integer")
    if (
        isinstance(schema.get("minLength"), int)
        and isinstance(schema.get("maxLength"), int)
        and schema["minLength"] > schema["maxLength"]
    ):
        errors.append(f"{path}.minLength must not exceed maxLength")
    if "pattern" in schema:
        pattern = schema.get("pattern")
        if not isinstance(pattern, str):
            errors.append(f"{path}.pattern must be a string")
        else:
            try:
                re.compile(pattern)
            except re.error:
                errors.append(f"{path}.pattern must be a valid regular expression")

    if expected == "object":
        properties = schema.get("properties")
        if not isinstance(properties, dict) or not properties:
            errors.append(f"{path}.properties must be a non-empty object")
            properties = {}
        required = schema.get("required", [])
        if (
            not isinstance(required, list)
            or any(not isinstance(item, str) or not item for item in required)
            or len(set(required)) != len(required)
        ):
            errors.append(f"{path}.required must contain unique non-empty strings")
            required = []
        unknown_required = sorted(set(required) - set(properties))
        if unknown_required:
            errors.append(f"{path}.required contains undeclared properties")
        additional = schema.get("additionalProperties")
        if additional is not False and not isinstance(additional, dict):
            errors.append(
                f"{path}.additionalProperties must be false or a typed schema"
            )
        elif isinstance(additional, dict):
            errors.extend(
                validate_field_schema_definition(
                    additional,
                    path=f"{path}.additionalProperties",
                    _depth=_depth + 1,
                )
            )
        for name, child in properties.items():
            if not isinstance(name, str) or not name:
                errors.append(f"{path}.properties keys must be non-empty strings")
                continue
            errors.extend(
                validate_field_schema_definition(
                    child,
                    path=f"{path}.{name}",
                    _depth=_depth + 1,
                )
            )
    elif expected == "array":
        items = schema.get("items")
        if not isinstance(items, dict):
            errors.append(f"{path}.items must be a typed schema")
        else:
            errors.extend(
                validate_field_schema_definition(
                    items,
                    path=f"{path}[]",
                    _depth=_depth + 1,
                )
            )
        for key in ("minItems", "maxItems"):
            if key in schema:
                value = schema.get(key)
                if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                    errors.append(f"{path}.{key} must be a non-negative integer")
        if (
            isinstance(schema.get("minItems"), int)
            and isinstance(schema.get("maxItems"), int)
            and schema["minItems"] > schema["maxItems"]
        ):
            errors.append(f"{path}.minItems must not exceed maxItems")
        if "uniqueItems" in schema and not isinstance(schema.get("uniqueItems"), bool):
            errors.append(f"{path}.uniqueItems must be boolean")
        if "x-order" in schema:
            if schema.get("x-order") not in {"nondecreasing", "strictly_increasing"}:
                errors.append(f"{path}.x-order is unsupported")
            elif not isinstance(items, dict) or items.get("type") not in {"integer", "number"}:
                errors.append(f"{path}.x-order requires numeric items")
    return errors


def validate_declared_field_schemas(
    payload: Any,
    output_contract: Any,
) -> list[FieldSchemaViolation]:
    """Validate present fields without exposing values or unknown key names."""
    if not isinstance(payload, dict) or not isinstance(output_contract, dict):
        return []
    schemas = declared_field_schemas(output_contract)
    violations: list[FieldSchemaViolation] = []

    def add(path: str, keyword: str, expected: str, actual: str) -> None:
        item = FieldSchemaViolation(path, keyword, expected, actual)
        if item not in violations:
            violations.append(item)

    def visit(value: Any, schema: dict[str, Any], path: str, depth: int) -> None:
        if depth > 8:
            add(path, "depth", "at_most_8", "too_deep")
            return
        expected = schema.get("type")
        if not isinstance(expected, str) or not value_matches_type(value, expected):
            add(path, "type", str(expected or "declared_type"), json_type_name(value))
            return
        if "enum" in schema and isinstance(schema.get("enum"), list):
            if not any(
                json_type_name(value) == json_type_name(allowed) and value == allowed
                for allowed in schema["enum"]
            ):
                add(path, "enum", "declared_values", "value_not_allowed")
        if "const" in schema:
            const = schema.get("const")
            if json_type_name(value) != json_type_name(const) or value != const:
                add(path, "const", "declared_value", "value_mismatch")
        if expected in {"integer", "number"}:
            minimum = schema.get("minimum")
            maximum = schema.get("maximum")
            if value_matches_type(minimum, "number") and value < minimum:
                add(path, "minimum", "at_or_above_minimum", "below_minimum")
            if value_matches_type(maximum, "number") and value > maximum:
                add(path, "maximum", "at_or_below_maximum", "above_maximum")
        if expected == "string":
            if isinstance(schema.get("minLength"), int) and len(value) < schema["minLength"]:
                add(path, "minLength", "at_or_above_min_length", "too_short")
            if isinstance(schema.get("maxLength"), int) and len(value) > schema["maxLength"]:
                add(path, "maxLength", "at_or_below_max_length", "too_long")
            if isinstance(schema.get("pattern"), str) and re.search(schema["pattern"], value) is None:
                add(path, "pattern", "pattern_match", "pattern_mismatch")
        if expected == "object":
            properties = schema.get("properties")
            if not isinstance(properties, dict):
                return
            required = schema.get("required")
            if isinstance(required, list):
                for name in required:
                    if isinstance(name, str) and name not in value:
                        add(f"{path}.{name}", "required", "present", "missing")
            additional = schema.get("additionalProperties", True)
            has_undeclared = any(name not in properties for name in value)
            if has_undeclared and additional is False:
                # Never include the provider-controlled key in public metadata.
                add(path, "additionalProperties", "none", "undeclared_property")
            for name, child in properties.items():
                if name in value and isinstance(child, dict):
                    visit(value[name], child, f"{path}.{name}", depth + 1)
            if isinstance(additional, dict):
                for name, child_value in value.items():
                    if name not in properties:
                        visit(child_value, additional, f"{path}.{{}}", depth + 1)
        elif expected == "array":
            if isinstance(schema.get("minItems"), int) and len(value) < schema["minItems"]:
                add(path, "minItems", "at_or_above_min_items", "too_few_items")
            if isinstance(schema.get("maxItems"), int) and len(value) > schema["maxItems"]:
                add(path, "maxItems", "at_or_below_max_items", "too_many_items")
            if schema.get("uniqueItems") is True:
                encoded = [json.dumps(item, sort_keys=True, ensure_ascii=False) for item in value]
                if len(set(encoded)) != len(encoded):
                    add(path, "uniqueItems", "unique", "duplicate_items")
            order = schema.get("x-order")
            if order in {"nondecreasing", "strictly_increasing"} and all(
                value_matches_type(item, "number") for item in value
            ):
                pairs = zip(value, value[1:])
                ordered = (
                    all(left <= right for left, right in pairs)
                    if order == "nondecreasing"
                    else all(left < right for left, right in pairs)
                )
                if not ordered:
                    add(path, "x-order", str(order), "out_of_order")
            items = schema.get("items")
            if isinstance(items, dict):
                for child_value in value:
                    visit(child_value, items, f"{path}[]", depth + 1)

    def resolve(base: Any, relation_path: str) -> Any:
        current: Any = base
        for part in relation_path.split("."):
            if not isinstance(current, dict) or part not in current:
                return _MISSING
            current = current[part]
        return current

    def same_json_value(left: Any, right: Any) -> bool:
        return json_type_name(left) == json_type_name(right) and left == right

    def predicate_matches(predicate: dict[str, Any], base: Any) -> bool:
        operator = predicate.get("operator")
        relation_path = predicate.get("path")
        if not isinstance(relation_path, str):
            return False
        value = resolve(base, relation_path)
        if operator == "present":
            return value is not _MISSING
        if operator == "absent":
            return value is _MISSING
        if value is _MISSING:
            return False
        if operator == "empty":
            return value in ("", [], {})
        if operator == "non_empty":
            return value not in ("", [], {})
        if operator == "equals":
            return same_json_value(value, predicate.get("value"))
        if operator == "not_equals":
            return not same_json_value(value, predicate.get("value"))
        if operator in {"in", "not_in"}:
            candidates = predicate.get("value")
            if not isinstance(candidates, list):
                return False
            matched = any(same_json_value(value, item) for item in candidates)
            return matched if operator == "in" else not matched
        if operator in {"gt", "gte", "lt", "lte"}:
            threshold = predicate.get("value")
            if not value_matches_type(value, "number") or not value_matches_type(
                threshold, "number"
            ):
                return False
            return {
                "gt": value > threshold,
                "gte": value >= threshold,
                "lt": value < threshold,
                "lte": value <= threshold,
            }[operator]
        if operator == "count_where_equals":
            if not isinstance(value, list):
                return False
            where = predicate.get("where")
            target = predicate.get("value")
            if not isinstance(where, list) or not value_matches_type(target, "integer"):
                return False
            count = sum(
                1
                for item in value
                if isinstance(item, dict)
                and all(
                    isinstance(child, dict) and predicate_matches(child, item)
                    for child in where
                )
            )
            return count == target
        if operator == "contains_field_equals_path":
            if not isinstance(value, list):
                return False
            item_path = predicate.get("item_path")
            other_path = predicate.get("other_path")
            where = predicate.get("where", [])
            if (
                not isinstance(item_path, str) or not isinstance(other_path, str)
                or not isinstance(where, list)
            ):
                return False
            target = resolve(base, other_path)
            if target is _MISSING:
                return False
            return any(
                isinstance(item, dict)
                and all(
                    isinstance(child, dict) and predicate_matches(child, item)
                    for child in where
                )
                and (
                    (candidate := resolve(item, item_path)) is not _MISSING
                    and same_json_value(candidate, target)
                )
                for item in value
            )
        if operator == "disjoint_fields":
            if not isinstance(value, list):
                return False
            other_path = predicate.get("other_path")
            item_path = predicate.get("item_path")
            other_item_path = predicate.get("other_item_path")
            if not all(
                isinstance(item, str)
                for item in (other_path, item_path, other_item_path)
            ):
                return False
            other_values = resolve(base, other_path)
            if not isinstance(other_values, list):
                return False
            left = [
                resolve(item, item_path)
                for item in value if isinstance(item, dict)
            ]
            right = [
                resolve(item, other_item_path)
                for item in other_values if isinstance(item, dict)
            ]
            return not any(
                left_value is not _MISSING and right_value is not _MISSING
                and same_json_value(left_value, right_value)
                for left_value in left for right_value in right
            )
        other_path = predicate.get("other_path")
        if not isinstance(other_path, str):
            return False
        other = resolve(base, other_path)
        if other is _MISSING:
            return False
        if operator == "equals_path":
            return same_json_value(value, other)
        if operator == "not_equals_path":
            return not same_json_value(value, other)
        if operator == "length_equals":
            return isinstance(value, list) and value_matches_type(other, "integer") and len(value) == other
        return False

    for field, schema in schemas.items():
        if field in payload:
            visit(payload[field], schema, field, 0)
    for relation in declared_field_relations(output_contract):
        when = relation.get("when")
        must = relation.get("must")
        if not isinstance(when, list) or not isinstance(must, list):
            continue
        for_each = relation.get("for_each")
        if isinstance(for_each, str):
            collection = resolve(payload, for_each)
            if not isinstance(collection, list):
                continue
            scopes = [item for item in collection if isinstance(item, dict)]
            path_prefix = f"{for_each}[]."
        else:
            scopes = [payload]
            path_prefix = ""
        for scope in scopes:
            if not all(
                isinstance(item, dict) and predicate_matches(item, scope)
                for item in when
            ):
                continue
            relation_id = relation.get("id")
            for predicate in must:
                if not isinstance(predicate, dict) or predicate_matches(predicate, scope):
                    continue
                relation_path = predicate.get("path")
                add(
                    path_prefix + relation_path
                    if isinstance(relation_path, str) else path_prefix.rstrip(".") or "$",
                    "fieldRelation",
                    str(relation_id or "declared_relation"),
                    f"{predicate.get('operator') or 'predicate'}_violated",
                )
    return violations


def validate_evidence_bindings(
    payload: Any,
    output_contract: Any,
    source_text: Any = None,
    *,
    source_documents: Any = None,
) -> list[FieldSchemaViolation]:
    """Bind evidence quotes to exact single- or multi-document slices."""
    if (
        not isinstance(payload, dict)
        or not isinstance(output_contract, dict)
    ):
        return []
    violations: list[FieldSchemaViolation] = []

    def add(path: str, binding_id: str, actual: str) -> None:
        item = FieldSchemaViolation(
            path=path,
            keyword="evidenceBinding",
            expected=binding_id,
            actual=actual,
        )
        if item not in violations:
            violations.append(item)

    def resolve(base: Any, declared_path: str) -> Any:
        current = base
        for part in declared_path.split("."):
            if not isinstance(current, dict) or part not in current:
                return _MISSING
            current = current[part]
        return current

    documents, document_errors = prepare_source_documents(
        source_documents,
        fallback_text=source_text,
    )
    for error in document_errors:
        if error not in violations:
            violations.append(error)
    documents_by_id: dict[str, list[PreparedSourceDocument]] = {}
    for document in documents:
        documents_by_id.setdefault(document.document_id, []).append(document)

    for binding in declared_evidence_bindings(output_contract):
        for_each = binding.get("for_each")
        text_path = binding.get("text_path")
        span_path = binding.get("span_path")
        start_path = binding.get("start_path")
        end_path = binding.get("end_path")
        document_id_path = binding.get("document_id_path")
        document_version_path = binding.get("document_version_path")
        binding_id = str(binding.get("id") or "declared_evidence_binding")
        if not all(isinstance(item, str) for item in (for_each, text_path)):
            continue
        collection = resolve(payload, for_each)
        if not isinstance(collection, list):
            continue
        for item in collection:
            if not isinstance(item, dict):
                continue
            evidence_text = resolve(item, text_path)
            public_text_path = f"{for_each}[].{text_path}"
            if not isinstance(evidence_text, str) or not evidence_text:
                add(public_text_path, binding_id, "empty_or_invalid_evidence_text")
                continue
            if isinstance(span_path, str):
                span = resolve(item, span_path)
                public_span_path = f"{for_each}[].{span_path}"
                if (
                    not isinstance(span, list)
                    or len(span) != 2
                    or not all(value_matches_type(value, "integer") for value in span)
                ):
                    add(public_span_path, binding_id, "invalid_span")
                    continue
                start, end = span
            elif isinstance(start_path, str) and isinstance(end_path, str):
                start = resolve(item, start_path)
                end = resolve(item, end_path)
                public_span_path = f"{for_each}[].{start_path}"
                if not (
                    value_matches_type(start, "integer")
                    and value_matches_type(end, "integer")
                ):
                    add(public_span_path, binding_id, "invalid_span")
                    continue
            else:
                continue

            target_document: PreparedSourceDocument | None = None
            if isinstance(document_id_path, str):
                document_id = resolve(item, document_id_path)
                public_document_path = f"{for_each}[].{document_id_path}"
                if not isinstance(document_id, str) or not document_id:
                    add(public_document_path, binding_id, "invalid_document_id")
                    continue
                candidates = documents_by_id.get(document_id, [])
                if isinstance(document_version_path, str):
                    document_version = resolve(item, document_version_path)
                    public_version_path = f"{for_each}[].{document_version_path}"
                    if not isinstance(document_version, str) or not document_version:
                        add(public_version_path, binding_id, "invalid_document_version")
                        continue
                    candidates = [
                        document for document in candidates
                        if document.document_version == document_version
                    ]
                    if not candidates:
                        add(public_version_path, binding_id, "document_version_not_found")
                        continue
                if not candidates:
                    add(public_document_path, binding_id, "document_not_found")
                    continue
                if len(candidates) != 1:
                    add(public_document_path, binding_id, "document_version_ambiguous")
                    continue
                target_document = candidates[0]
            elif isinstance(source_text, str):
                target_document = PreparedSourceDocument(
                    document_id="input",
                    text=source_text,
                )
            elif len(documents) == 1:
                target_document = documents[0]
            else:
                add(public_text_path, binding_id, "source_document_required")
                continue

            target_text = target_document.text
            if start < 0 or end <= start or end > len(target_text):
                add(public_span_path, binding_id, "out_of_source_bounds")
                continue
            if target_text[start:end] != evidence_text:
                add(public_text_path, binding_id, "source_text_mismatch")
    return violations


def validate_cross_agent_relations(
    payload: Any,
    output_contract: Any,
    upstream_results: Any,
) -> list[FieldSchemaViolation]:
    """Validate local output against explicitly supplied upstream Agent results."""
    if not isinstance(payload, dict) or not isinstance(output_contract, dict):
        return []
    violations: list[FieldSchemaViolation] = []

    def add(path: str, relation_id: str, actual: str) -> None:
        item = FieldSchemaViolation(
            path=path,
            keyword="crossAgentRelation",
            expected=relation_id,
            actual=actual,
        )
        if item not in violations:
            violations.append(item)

    def resolve(base: Any, declared_path: str) -> Any:
        current = base
        for part in declared_path.split("."):
            if not isinstance(current, dict) or part not in current:
                return _MISSING
            current = current[part]
        return current

    upstream_by_agent: dict[str, list[dict[str, Any]]] = {}
    if isinstance(upstream_results, list):
        for item in upstream_results:
            if not isinstance(item, dict):
                continue
            agent_id = item.get("agent_id")
            result = item.get("result")
            if isinstance(agent_id, str) and isinstance(result, dict):
                upstream_by_agent.setdefault(agent_id, []).append(result)

    def item_values(collection: Any, item_path: str) -> list[Any]:
        if not isinstance(collection, list):
            return []
        values: list[Any] = []
        for item in collection:
            value = resolve(item, item_path) if isinstance(item, dict) else _MISSING
            if value is not _MISSING:
                values.append(value)
        return values

    def normalized(value: Any, mode: str) -> Any:
        if mode != "medical_code" or not isinstance(value, str):
            return value
        return "".join(
            unicodedata.normalize("NFKC", value).strip().upper().split()
        )

    for relation in declared_cross_agent_relations(output_contract):
        relation_id = str(relation.get("id") or "declared_cross_agent_relation")
        local_path = relation.get("local_path")
        upstream_agent_id = relation.get("upstream_agent_id")
        upstream_path = relation.get("upstream_path")
        upstream_item_path = relation.get("upstream_item_path")
        operator = relation.get("operator")
        normalization = str(relation.get("normalization") or "none")
        required_strings = [local_path, upstream_agent_id, operator]
        if operator != "local_items_subset_upstream_values":
            required_strings.extend([upstream_path, upstream_item_path])
        if not all(isinstance(value, str) for value in required_strings):
            continue
        upstream_candidates = upstream_by_agent.get(upstream_agent_id, [])
        if not upstream_candidates:
            if relation.get("required") is True:
                add(local_path, relation_id, "required_upstream_missing")
            continue
        if len(upstream_candidates) != 1:
            add(local_path, relation_id, "upstream_result_ambiguous")
            continue
        local_value = resolve(payload, local_path)
        if operator == "local_items_subset_upstream_values":
            raw_upstream_values: list[Any] = []
            for source in relation.get("upstream_sources") or []:
                if not isinstance(source, dict):
                    continue
                source_path = source.get("path")
                if not isinstance(source_path, str):
                    continue
                source_value = resolve(upstream_candidates[0], source_path)
                item_path = source.get("item_path")
                if isinstance(item_path, str):
                    raw_upstream_values.extend(item_values(source_value, item_path))
                elif isinstance(source_value, list):
                    raw_upstream_values.extend(source_value)
                elif source_value is not _MISSING:
                    raw_upstream_values.append(source_value)
            upstream_values = [
                normalized(value, normalization) for value in raw_upstream_values
            ]
        else:
            upstream_collection = resolve(upstream_candidates[0], upstream_path)
            upstream_values = [
                normalized(value, normalization)
                for value in item_values(upstream_collection, upstream_item_path)
            ]
        local_value = normalized(local_value, normalization)
        matched = False
        if operator == "equals_upstream":
            upstream_value = normalized(
                resolve(upstream_candidates[0], upstream_path),
                normalization,
            )
            matched = local_value is not _MISSING and local_value == upstream_value
        elif operator == "scalar_in_upstream_items":
            matched = local_value is not _MISSING and local_value in upstream_values
        else:
            local_values = [
                normalized(value, normalization)
                for value in item_values(
                    resolve(payload, local_path),
                    str(relation.get("local_item_path") or ""),
                )
            ]
            local_set = set(json.dumps(value, sort_keys=True, ensure_ascii=False) for value in local_values)
            upstream_set = set(
                json.dumps(value, sort_keys=True, ensure_ascii=False)
                for value in upstream_values
            )
            allow_empty_local = relation.get("allow_empty_local") is True
            if operator in {
                "local_items_subset_upstream_items",
                "local_items_subset_upstream_values",
            }:
                matched = local_set <= upstream_set and (
                    bool(local_set) or allow_empty_local
                )
            elif operator == "local_items_overlap_upstream_items":
                matched = bool(local_set & upstream_set)
        if not matched:
            add(local_path, relation_id, f"{operator}_violated")
    return violations
