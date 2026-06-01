"""iCoDer CLI — command-line tools for Agent development.

Usage:
    icoder-runtime init <name>     Scaffold a new agent project
    icoder-runtime test <path>     Test an agent locally
    icoder-runtime pack <path>     Export agent as .icoder-agent
    icoder-runtime serve           Start HTTP server
    icoder-runtime dashboard       Start local Web UI
"""

import argparse
import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

def _agent_json(name: str) -> str:
    return json.dumps({
        "name": name,
        "version": "1.0.0",
        "description": "A custom compliance agent.",
        "category": "compliance",
        "icon": "Shield",
    }, indent=2, ensure_ascii=False)

def _perm_json() -> str:
    return json.dumps({
        "key": "default",
        "name": "Default",
        "description": "Default permission preset",
        "tools": {},
    }, indent=2, ensure_ascii=False)

AGENT_FILES = [
    ("agent.json", _agent_json, True),
    ("system_prompt.md", lambda n: f"# {n}\n\nYou are a compliance auditing specialist.\n\n## Output Format\n\n1. ...\n2. ...\n", False),
    ("permissions.json", lambda n: _perm_json(), True),
    ("README.md", lambda n: f"# {n}\n\n## Setup\n```bash\npip install icoder-runtime\nicoder test .\n```\n\n## Build\n```bash\nicoder pack .\n```\n", False),
]


def main():
    parser = argparse.ArgumentParser(description="iCoDer Runtime CLI")
    sub = parser.add_subparsers(dest="command")

    # init
    p_init = sub.add_parser("init", help="Scaffold a new agent project")
    p_init.add_argument("name", help="Agent name")

    # test
    p_test = sub.add_parser("test", help="Test an agent locally")
    p_test.add_argument("path", default=".", nargs="?", help="Path to agent directory")

    # pack
    p_pack = sub.add_parser("pack", help="Export agent as .icoder-agent")
    p_pack.add_argument("path", default=".", nargs="?", help="Path to agent directory")
    p_pack.add_argument("-o", "--output", help="Output file path")

    # serve (handled by serve.py)
    p_serve = sub.add_parser("serve", help="Start HTTP server")
    p_serve.add_argument("--port", type=int, default=8765)
    p_serve.add_argument("--host", default="127.0.0.1")

    # dashboard
    p_dash = sub.add_parser("dashboard", help="Start local Web UI")
    p_dash.add_argument("--port", type=int, default=8766)

    args = parser.parse_args()

    if args.command == "init":
        cmd_init(args.name)
    elif args.command == "test":
        cmd_test(args.path)
    elif args.command == "pack":
        cmd_pack(args.path, args.output)
    elif args.command == "serve":
        from .serve import main as serve_main
        sys.argv = ["icoder-runtime", "--port", str(args.port), "--host", args.host]
        serve_main()
    elif args.command == "dashboard":
        cmd_dashboard(args.port)
    else:
        parser.print_help()


def cmd_init(name: str):
    """Scaffold a new agent directory."""
    path = Path(name)
    if path.exists():
        print(f"Error: Directory '{name}' already exists.")
        sys.exit(1)

    path.mkdir(parents=True)
    (path / "tools").mkdir()

    for filename, content_fn, is_json in AGENT_FILES:
        content = content_fn(name)
        filepath = path / filename
        filepath.write_text(content, encoding="utf-8")

    print(f"Agent project created: {path.absolute()}")
    print(f"  {path / 'agent.json'}")
    print(f"  {path / 'system_prompt.md'}")
    print(f"  {path / 'tools/'}")
    print(f"  {path / 'permissions.json'}")
    print(f"\nNext: cd {name} && icoder-runtime test .")


def cmd_test(dir_path: str):
    """Run a local agent pack test."""
    from .agent_pack import load_pack, validate_pack, import_pack
    from .agent_runner import AgentRunner
    import asyncio

    path = Path(dir_path).resolve()
    if not path.exists():
        print(f"Error: Directory '{dir_path}' not found.")
        sys.exit(1)

    # Find agent.json
    agent_file = path / "agent.json"
    if not agent_file.exists():
        print(f"Error: agent.json not found in '{path}'.")
        print("Run 'icoder-runtime init <name>' first.")
        sys.exit(1)

    # Load and validate
    try:
        pack_data = json.loads(agent_file.read_text(encoding="utf-8"))
        # Build full pack from directory
        pack = _build_pack_from_dir(path, pack_data)
    except json.JSONDecodeError as e:
        print(f"Error: invalid JSON in agent.json: {e}")
        sys.exit(1)

    errors = validate_pack(pack)
    if errors:
        print(f"Validation errors ({len(errors)}):")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)

    agent, experts, tools, perm = import_pack(pack)
    print(f"Loaded: {agent.name} v{agent.version}")
    print(f"  Experts: {len(experts)}")
    print(f"  Tools: {len(tools)}")

    # Run test
    test_input = "患者女性，65岁。胸痛3小时入院。心电图示ST段抬高。诊断为急性前壁心肌梗死。"
    print(f"\nTest input: {test_input[:60]}...")

    runner = AgentRunner()
    for e in experts:
        runner.register_expert(e)
    for t in tools:
        runner.register_tool(t)

    result = asyncio.run(runner.run(agent, test_input))
    print(f"\nResult:")
    print(f"  Review ID: {result['review_id']}")
    print(f"  Processing: {result['processing_time_ms']}ms")
    print(f"  Audit entries: {result['state_log']['entry_count']}")
    print(f"  Chain valid: {result['state_log']['chain_valid']}")
    print(f"\nTest PASSED.")


def cmd_pack(dir_path: str, output: str | None):
    """Export agent directory as .icoder-agent file."""
    from .agent_pack import save_pack

    path = Path(dir_path).resolve()
    agent_file = path / "agent.json"
    if not agent_file.exists():
        print(f"Error: agent.json not found in '{path}'.")
        sys.exit(1)

    try:
        pack_data = json.loads(agent_file.read_text(encoding="utf-8"))
        pack = _build_pack_from_dir(path, pack_data)
    except json.JSONDecodeError as e:
        print(f"Error: invalid JSON: {e}")
        sys.exit(1)

    output_path = save_pack(pack, output or f"{pack_data.get('name', 'agent')}.icoder-agent")
    print(f"Pack exported: {output_path.absolute()}")
    print(f"  SHA256: {pack['integrity']['sha256'][:30]}...")


def cmd_dashboard(port: int):
    """Start local dashboard with Web UI."""
    from .serve import main as serve_main
    import sys
    sys.argv = ["icoder-dashboard", "--port", str(port), "--host", "127.0.0.1"]
    serve_main()


def _build_pack_from_dir(dir_path: Path, agent_data: dict) -> dict:
    """Build a full pack from an agent directory."""
    from .agent_pack import export_pack
    from .types import AgentDefinition, ExpertDefinition, ToolDefinition, ToolTier

    name = agent_data.get("name", dir_path.name)
    # Use directory basename if name looks like a path
    if "/" in name or "\\" in name:
        name = dir_path.name
    agent = AgentDefinition(
        name=name,
        version=agent_data.get("version", "1.0.0"),
        description=agent_data.get("description", ""),
        category=agent_data.get("category", "general"),
        icon=agent_data.get("icon", "Bot"),
        system_prompt=_read_file(dir_path / "system_prompt.md"),
        expert_ids=agent_data.get("expert_ids", []),
        config=agent_data.get("config", {}),
    )

    # Load custom tools
    tools = []
    tools_dir = dir_path / "tools"
    if tools_dir.exists():
        for tf in tools_dir.glob("*.json"):
            try:
                tdata = json.loads(tf.read_text(encoding="utf-8"))
                tools.append(ToolDefinition(
                    id=tdata.get("id", tf.stem),
                    name=tdata["name"],
                    description=tdata.get("description", ""),
                    tier=ToolTier(tdata.get("tier", 1)),
                    category=tdata.get("category", "custom"),
                    icon=tdata.get("icon", "Wrench"),
                    requires=tdata.get("requires", []),
                    guarantees=tdata.get("guarantees", {}),
                    input_schema={"type": "object", "properties": tdata.get("params", {})} if tdata.get("params") else None,
                    accuracy_tags=tdata.get("accuracy_tags", []),
                    is_injectable=tdata.get("is_injectable", False),
                ))
            except Exception as e:
                logger.warning(f"Skipping {tf.name}: {e}")

    # Load permissions
    perm = {}
    perm_file = dir_path / "permissions.json"
    if perm_file.exists():
        try:
            perm = json.loads(perm_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    return export_pack(agent, tools=tools, permission=perm)


def _read_file(path: Path) -> str:
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return ""


if __name__ == "__main__":
    main()
