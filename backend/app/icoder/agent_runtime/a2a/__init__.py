"""iCoDer A2A v0.3 Protocol Implementation (SPEC §3).

Phase 1 subset: ``message/send`` (inbound + outbound stub) +
``tasks/get`` / ``tasks/cancel`` stubs + 4 Discovery endpoints.

Public API (re-exported):

- :mod:`.envelope` — JSON-RPC 2.0 envelope (parse/serialize)
- :mod:`.errors` — A2A v0.3 error codes (8 business + 5 standard)
- :mod:`.parts` — TextPart / DataPart / FilePart (FilePart rejected)
- :mod:`.messages` — A2A Message / Task
- :mod:`.agent_card` — AgentCard + substructures + homepage factory
- :mod:`.icoder_metadata` — iCoDer metadata types (Run / Delegation)
- :mod:`.schema_registry` — iCoDer schema identifier resolver
- :mod:`.version` — A2A protocol version negotiation

Routing factories live in ``routes_*.py`` modules and are mounted via
``mount_a2a(app, ...)`` in ``a2a_routes.py`` (Phase 1 commit 2).
"""

from .agent_card import (
    AgentCapabilities,
    AgentCard,
    AgentListResponse,
    AgentSkill,
    SecurityScheme,
    medcoder_coding_review_card,
)
from .envelope import (
    SUPPORTED_METHODS,
    SUPPORTED_TASKS_METHODS,
    EnvelopeParseError,
    JsonRpcRequest,
    JsonRpcResponse,
    make_error_response,
    make_parse_error_response,
    make_success_response,
    parse_request,
    validate_method,
)
from .errors import (
    ALL_A2A_ERROR_CODES,
    A2AError,
    A2AErrorCode,
    JSON_RPC_INTERNAL_ERROR,
    JSON_RPC_INVALID_PARAMS,
    JSON_RPC_INVALID_REQUEST,
    JSON_RPC_METHOD_NOT_FOUND,
    JSON_RPC_PARSE_ERROR,
    agent_not_found,
    context_invalid,
    context_not_found,
    internal_error,
    invalid_params,
    invalid_request,
    method_not_found,
    phi_redaction_failed,
    production_writeback_blocked,
    task_not_cancelable,
    task_not_found,
    unsupported_operation,
)
from .icoder_metadata import (
    ALL_ICODER_SCHEMAS,
    DelegationMetadata,
    RunMetadata,
    SCHEMA_COMPLIANCE_OUTPUT,
    SCHEMA_DRG_GROUPING_OUTPUT,
    SCHEMA_EVIDENCE_SPAN,
    SCHEMA_MEDICAL_CODING_INPUT,
    SCHEMA_MEDICAL_CODING_OUTPUT,
)
from .messages import (
    A2AMessage,
    A2ATask,
    A2ATaskStatus,
    parse_message,
    parse_params,
    serialize_message_envelope,
)
from .parts import (
    DataPart,
    FilePart,
    Part,
    PartKind,
    TextPart,
    parse_part,
    parse_parts,
    parts_to_envelope_dicts,
)
from .schema_registry import (
    known_schema,
    list_schemas,
    resolve_schema,
)
from .version import (
    A2A_PROTOCOL_HEADER,
    A2A_PROTOCOL_VERSION,
    A2AVersionError,
    SUPPORTED_VERSIONS,
    negotiate_version,
    validate_version_header,
)
from .a2a_routes import build_a2a_routers, mount_a2a
from .routes_context import build_context_router
from .routes_discovery import AgentProvider, build_discovery_router
from .routes_inbound import build_inbound_router
from .routes_outbound import ExpertCaller, build_outbound_router
from .routes_task import build_task_router

__all__ = [
    # Errors
    "ALL_A2A_ERROR_CODES",
    "A2AError",
    "A2AErrorCode",
    "JSON_RPC_INTERNAL_ERROR",
    "JSON_RPC_INVALID_PARAMS",
    "JSON_RPC_INVALID_REQUEST",
    "JSON_RPC_METHOD_NOT_FOUND",
    "JSON_RPC_PARSE_ERROR",
    "agent_not_found",
    "context_invalid",
    "context_not_found",
    "internal_error",
    "invalid_params",
    "invalid_request",
    "method_not_found",
    "phi_redaction_failed",
    "production_writeback_blocked",
    "task_not_cancelable",
    "task_not_found",
    "unsupported_operation",
    # Envelope
    "EnvelopeParseError",
    "JsonRpcRequest",
    "JsonRpcResponse",
    "SUPPORTED_METHODS",
    "SUPPORTED_TASKS_METHODS",
    "make_error_response",
    "make_parse_error_response",
    "make_success_response",
    "parse_request",
    "validate_method",
    # Parts
    "DataPart",
    "FilePart",
    "Part",
    "PartKind",
    "TextPart",
    "parse_part",
    "parse_parts",
    "parts_to_envelope_dicts",
    # Messages
    "A2AMessage",
    "A2ATask",
    "A2ATaskStatus",
    "parse_message",
    "parse_params",
    "serialize_message_envelope",
    # Agent Card
    "AgentCapabilities",
    "AgentCard",
    "AgentListResponse",
    "AgentSkill",
    "SecurityScheme",
    "medcoder_coding_review_card",
    # iCoDer metadata
    "ALL_ICODER_SCHEMAS",
    "DelegationMetadata",
    "RunMetadata",
    "SCHEMA_COMPLIANCE_OUTPUT",
    "SCHEMA_DRG_GROUPING_OUTPUT",
    "SCHEMA_EVIDENCE_SPAN",
    "SCHEMA_MEDICAL_CODING_INPUT",
    "SCHEMA_MEDICAL_CODING_OUTPUT",
    # Schema registry
    "known_schema",
    "list_schemas",
    "resolve_schema",
    # Version
    "A2A_PROTOCOL_HEADER",
    "A2A_PROTOCOL_VERSION",
    "A2AVersionError",
    "SUPPORTED_VERSIONS",
    "negotiate_version",
    "validate_version_header",
    # Routes (Commit 2)
    "AgentProvider",
    "ExpertCaller",
    "build_a2a_routers",
    "build_context_router",
    "build_discovery_router",
    "build_inbound_router",
    "build_outbound_router",
    "build_task_router",
    "mount_a2a",
]