"""Contract Engine — symbolic state + pre/post-condition evaluation.

The contract engine enforces Hoare-style {P} t {Q} contracts on tool calls:
- Preconditions (P): what must be true in SymbolicState before a tool can execute
- Postconditions (Q): what must be true about a tool's output before it's committed

Key invariant: SymbolicState can only be modified through verified post_checks.
This prevents LLM-hallucinated data from corrupting the trusted world state.
"""

import logging
from enum import Enum

logger = logging.getLogger(__name__)


class ContractResult(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


class ContractViolation(Exception):
    """Raised when a tool call violates its contract."""

    def __init__(self, tool_id: str, stage: str, reason: str, suggestion: str = ""):
        self.tool_id = tool_id
        self.stage = stage  # "precondition" | "postcondition"
        self.reason = reason
        self.suggestion = suggestion
        super().__init__(f"[{stage}] {tool_id}: {reason}")

    def to_feedback(self) -> str:
        """Generate structured feedback for LLM to correct its plan."""
        msg = f"Tool '{self.tool_id}' rejected at {self.stage}: {self.reason}."
        if self.suggestion:
            msg += f" Suggestion: {self.suggestion}."
        return msg


class SymbolicState:
    """Typed, trusted world state that evolves only through verified tool executions.

    This is the deterministic "source of truth" for the Agent's world model.
    LLM reasoning reads from it; only post-verified tool results write to it.
    """

    def __init__(self, initial: dict | None = None):
        self._data: dict = initial or {}
        self._update_count: int = 0
        self._update_log: list[dict] = []  # Append-only log of verified updates

    def get(self, key: str, default=None):
        """Read from state. Supports dot-notation: 'evidence.diagnosis_facts'."""
        keys = key.split(".")
        current = self._data
        for k in keys:
            if isinstance(current, dict):
                current = current.get(k)
            else:
                return default
            if current is None:
                return default
        return current

    def has(self, key: str) -> bool:
        """Check if a key exists and is non-empty/non-None."""
        val = self.get(key)
        if val is None:
            return False
        if isinstance(val, (list, dict, str)):
            return len(val) > 0
        return True

    def merge(self, updates: dict, tool_id: str = "unknown") -> None:
        """Commit verified tool output to state. Only called by post_check on ALLOW."""
        self._data.update(updates)
        self._update_count += 1
        self._update_log.append({
            "update_id": self._update_count,
            "tool": tool_id,
            "keys": list(updates.keys()),
        })

    def snapshot(self) -> dict:
        """Return a shallow copy of current state."""
        return dict(self._data)

    def __repr__(self) -> str:
        keys = list(self._data.keys())
        return f"SymbolicState(keys={keys}, updates={self._update_count})"


def evaluate_precondition(expr: str, state: SymbolicState) -> tuple[ContractResult, str]:
    """Evaluate a precondition expression against the current symbolic state.

    Supported expressions:
    - "state.has('key')" — key exists and is non-empty
    - "state.has('key.subkey')" — dot-notation support
    - "expr1 and expr2" — logical AND
    - "expr1 or expr2" — logical OR

    Returns (ALLOW, "") or (DENY, reason_string).
    """
    if not expr or not expr.strip():
        return ContractResult.ALLOW, ""

    try:
        result = _eval_expr(expr.strip(), state)
        if result:
            return ContractResult.ALLOW, ""
        return ContractResult.DENY, f"Precondition not met: {expr}"
    except Exception as e:
        logger.warning(f"Precondition evaluation error: {e} for expr: {expr}")
        return ContractResult.DENY, f"Precondition evaluation failed: {e}"


def _eval_expr(expr: str, state: SymbolicState) -> bool:
    """Simple expression evaluator for preconditions."""
    expr = expr.strip()

    # Handle 'or'
    if " or " in expr:
        parts = expr.split(" or ", 1)
        return _eval_expr(parts[0], state) or _eval_expr(parts[1], state)

    # Handle 'and'
    if " and " in expr:
        parts = [p.strip() for p in expr.split(" and ")]
        return all(_eval_expr(p, state) for p in parts)

    # Handle state.has('...')
    if expr.startswith("state.has(") and expr.endswith(")"):
        inner = expr[len("state.has("):-1].strip().strip("'").strip('"')
        return state.has(inner)

    # Handle bare key reference (same as state.has)
    return state.has(expr)


def validate_postcondition(
    guarantee_spec: str, result: dict, state: SymbolicState
) -> tuple[ContractResult, str]:
    """Validate a postcondition guarantee against the tool's output.

    Supported guarantee specs:
    - "output.key" — key must exist in result (non-None)
    - "output.key: valid <format>" — key must exist and match format hint
    - "output.key: non-empty" — key must be non-empty
    - "output.key: min_length N" — list/string must have minimum length

    Returns (ALLOW, "") or (DENY, reason_string).
    """
    if not guarantee_spec:
        return ContractResult.ALLOW, ""

    spec = guarantee_spec.strip()

    # Parse: "output.key: constraint" or "output.key"
    if ":" in spec:
        path, constraint = spec.split(":", 1)
        path = path.strip()
        constraint = constraint.strip()
    else:
        path = spec.strip()
        constraint = "exists"

    # Get value from result using dot notation
    parts = path.split(".")
    if parts[0] != "output":
        return ContractResult.DENY, f"Invalid guarantee path: {path} (must start with 'output')"

    value = result
    for part in parts[1:]:
        if isinstance(value, dict):
            value = value.get(part)
        elif isinstance(value, list) and part.isdigit():
            value = value[int(part)]
        else:
            return ContractResult.DENY, f"Path '{path}' not found in output"
        if value is None:
            return ContractResult.DENY, f"Path '{path}' is None"

    # Validate constraint
    if constraint == "exists":
        return ContractResult.ALLOW, ""

    if constraint == "non-empty":
        if isinstance(value, (list, dict, str)) and len(value) == 0:
            return ContractResult.DENY, f"Path '{path}' is empty"
        return ContractResult.ALLOW, ""

    if constraint.startswith("min_length "):
        try:
            min_len = int(constraint.split()[1])
            if len(value) < min_len:
                return ContractResult.DENY, f"Path '{path}' length {len(value)} < {min_len}"
        except (ValueError, TypeError):
            return ContractResult.DENY, f"Cannot check length of '{path}'"
        return ContractResult.ALLOW, ""

    if constraint.startswith("valid "):
        valid_type = constraint.split(" ", 1)[1]
        if valid_type == "icd10_code":
            if not isinstance(value, str) or not _is_valid_icd10(value):
                return ContractResult.DENY, f"Path '{path}' is not a valid ICD-10 code: {value}"
        elif valid_type == "list":
            if not isinstance(value, list):
                return ContractResult.DENY, f"Path '{path}' is not a list"
        elif valid_type == "dict":
            if not isinstance(value, dict):
                return ContractResult.DENY, f"Path '{path}' is not a dict"
        elif valid_type == "string":
            if not isinstance(value, str):
                return ContractResult.DENY, f"Path '{path}' is not a string"
        return ContractResult.ALLOW, ""

    # Unknown constraint — warn but allow (don't block on unknown constraints)
    logger.warning(f"Unknown postcondition constraint: {constraint}")
    return ContractResult.ALLOW, ""


def _is_valid_icd10(code: str) -> bool:
    """Check if a string looks like a valid ICD-10 code."""
    if not code or len(code) < 3:
        return False
    # ICD-10-CM: letter + 2 digits, optionally .digit(s)
    # ICD-10-CN: letter + 2 digits, optionally .xxx
    import re
    return bool(re.match(r'^[A-Z]\d{2}(\.\d{1,4})?$', code))


def validate_tool_params(tool_id: str, params: dict, required_params: list[str]) -> tuple[ContractResult, str]:
    """Validate that required parameters are present."""
    missing = [p for p in required_params if p not in params or params[p] is None]
    if missing:
        return ContractResult.DENY, f"Missing required parameters: {missing}"
    return ContractResult.ALLOW, ""


# Singleton
contract_engine = None  # Instantiated when needed, not at import time
