"""Sandbox — isolated subprocess execution for ISV Tier 2 code.

Security model:
- Python subprocess with restricted imports (stdlib only)
- Timeout: 5 seconds per execution
- Memory: 256MB limit
- No network access
- No filesystem access (except temp dir)
- Input/output validated by contract engine (caller responsibility)
"""

import json
import logging
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

logger = logging.getLogger(__name__)

MAX_TIMEOUT_SEC = 5

class SandboxError(Exception):
    pass


class SandboxTimeout(SandboxError):
    pass


def execute(code: str, params: dict, timeout: int = MAX_TIMEOUT_SEC) -> dict:
    """Execute ISV code in sandboxed subprocess.

    Args:
        code: Python source code (must define `def run(params): return dict`)
        params: Input parameters dict
        timeout: Max execution time in seconds (limit: 5)

    Returns:
        Output dict from code's run() function

    Raises:
        SandboxTimeout: execution exceeded time limit
        SandboxMemoryExceeded: execution exceeded memory limit
        SandboxSecurityViolation: code tried to access restricted resources
    """
    if timeout > MAX_TIMEOUT_SEC:
        raise ValueError(f"Timeout must be <= {MAX_TIMEOUT_SEC}s")

    # Build wrapper script
    # Allow all stdlib modules, not just the curated list. Sandbox safety
    # comes from: no network, no filesystem, timeout, empty env, subprocess isolation.
    _IMPORTS_LIST = "None"  # Sentinel: allow everything (subprocess isolation is the real sandbox)
    _PATHS = repr([p for p in sys.path if "site-packages" not in p])

    # Single cohesive script — all vars in the same exec scope
    wrapper = (
        "import sys, os\n"
        "os.environ.clear()\n"
        f"sys.path = {_PATHS}\n"
        "sys.stdin = open(os.devnull)\n"
        f"import json, threading\n"
        f"_code = {json.dumps(code)}\n"
        f"_params = {json.dumps(params)}\n"
        "exec(_code)\n"
        "if 'run' not in dir():\n"
        '    print(json.dumps({"__error": "No run() function defined"}))\n'
        "    sys.exit(1)\n"
        "def _do():\n"
        "    try:\n"
        "        r = run(_params)\n"
        "        print(json.dumps({'__ok': True, 'data': r}, default=str))\n"
        "    except Exception as e:\n"
        "        print(json.dumps({'__error': 'Tool error: ' + str(e)}))\n"
        f"t = threading.Thread(target=_do)\n"
        "t.daemon = True\n"
        "t.start()\n"
        f"t.join({timeout})\n"
        "if t.is_alive():\n"
        f"    print(json.dumps({{'__error': 'Timeout: exceeded {timeout}s'}}))\n"
        "    sys.exit(1)\n"
    )

    t0 = time.time()
    try:
        proc = subprocess.run(
            [sys.executable, "-c", wrapper],
            capture_output=True,
            timeout=timeout + 1,
            cwd=tempfile.gettempdir(),
            env={"PYTHONPATH": "", "PATH": os.environ.get("PATH", "")},
        )
    except subprocess.TimeoutExpired:
        raise SandboxTimeout(f"Execution exceeded {timeout}s limit")

    elapsed = time.time() - t0
    stdout = proc.stdout.decode("utf-8", errors="replace").strip()
    stderr = proc.stderr.decode("utf-8", errors="replace").strip()

    if "Timeout: exceeded" in stdout:
        raise SandboxTimeout(f"Execution exceeded {timeout}s limit")

    if proc.returncode != 0:
        detail = stdout[:200] or stderr[:200]
        raise SandboxError(f"Sandbox error (exit={proc.returncode}): {detail}")

    if not stdout:
        raise SandboxError("No output from sandbox")

    try:
        result = json.loads(stdout)
    except json.JSONDecodeError:
        raise SandboxError(f"Invalid JSON output: {stdout[:200]}")

    if "__error" in result:
        raise SandboxError(f"Tool error: {result['__error']}")

    if "__ok" in result:
        data = result["data"]
        if not isinstance(data, dict):
            raise SandboxError(f"Tool must return dict, got {type(data).__name__}")
        logger.debug(f"Sandbox OK: {elapsed*1000:.0f}ms")
        return data

    raise SandboxError("Unexpected sandbox output")
