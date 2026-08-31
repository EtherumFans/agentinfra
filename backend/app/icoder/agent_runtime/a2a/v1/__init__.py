"""A2A v1.0 compatibility layer.

The v0.3 wire contract remains implemented by the parent package.  This
subpackage owns the breaking v1.0 ProtoJSON shapes and adapters so a v1
request can never silently change the meaning of an existing v0.3 route.
"""

from .protocol import (
    A2A_V1_HEADER,
    A2A_V1_VERSION,
    A2AV1ProtocolError,
    CanonicalMessage,
    CanonicalPart,
    SUPPORTED_V1_METHODS,
    decode_task_cursor,
    encode_task_cursor,
    parse_v1_jsonrpc,
    parse_v1_message,
    project_v0_3_message,
    project_v0_3_task,
    validate_v1_version,
)
from .routes import build_v1_router

__all__ = [
    "A2A_V1_HEADER",
    "A2A_V1_VERSION",
    "A2AV1ProtocolError",
    "CanonicalMessage",
    "CanonicalPart",
    "SUPPORTED_V1_METHODS",
    "build_v1_router",
    "decode_task_cursor",
    "encode_task_cursor",
    "parse_v1_jsonrpc",
    "parse_v1_message",
    "project_v0_3_message",
    "project_v0_3_task",
    "validate_v1_version",
]
