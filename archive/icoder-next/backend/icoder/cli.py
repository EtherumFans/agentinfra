"""``icoder`` CLI — the ISV/operator surface for Agent 打包/分发 (Phase 4).

Mirrors the full product's ``icoder pack`` tooling over the slice's stdlib pack format::

    python -m icoder.cli pack    <agent_id> [--out DIR]
    python -m icoder.cli publish <pack_path> [--market DIR]
    python -m icoder.cli install <agent_id> [--version V] [--market DIR]
    python -m icoder.cli list    [--market DIR]

``main(argv)`` returns an int exit code and is importable, so tests drive it in-process.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .runtime import pack as packlib
from .runtime.registry import default_registry

# backend/data/marketplace — data/ is gitignored; never committed.
_DEFAULT_MARKET = str(Path(__file__).resolve().parents[1] / "data" / "marketplace")


def _cmd_pack(args: argparse.Namespace) -> int:
    reg = default_registry()
    agent = reg.get(args.agent_id)
    if agent is None:
        print(f"error: 未注册的 agent {args.agent_id!r}", file=sys.stderr)
        return 2
    path = packlib.pack(agent, args.out)
    print(f"packed {agent.id}@{agent.version} -> {path}")
    return 0


def _cmd_publish(args: argparse.Namespace) -> int:
    market = packlib.Marketplace(args.market)
    entry = market.publish(args.pack_path)
    print(f"published {entry['id']}@{entry['version']} -> {market.packs_dir / entry['filename']}")
    return 0


def _cmd_install(args: argparse.Namespace) -> int:
    market = packlib.Marketplace(args.market)
    agent = market.install(args.agent_id, default_registry(), version=args.version)
    print(f"installed {agent.id}@{agent.version} "
          f"(experts={','.join(agent.experts)}; rule_sets={','.join(agent.rule_sets)})")
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    entries = packlib.Marketplace(args.market).list()
    if not entries:
        print("(marketplace 为空)")
        return 0
    for e in entries:
        print(f"{e['id']}@{e['version']}  {e['name']}  [{e['category']}]  {e['digest'][:19]}…")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="icoder", description="iCoDer Agent 打包/分发 CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("pack", help="把已注册的 thin Agent 打成 .icoder-agent 包")
    sp.add_argument("agent_id")
    sp.add_argument("--out", default=".", help="输出目录（默认当前目录）")
    sp.set_defaults(func=_cmd_pack)

    sp = sub.add_parser("publish", help="把 .icoder-agent 包发布到 marketplace")
    sp.add_argument("pack_path")
    sp.add_argument("--market", default=_DEFAULT_MARKET)
    sp.set_defaults(func=_cmd_publish)

    sp = sub.add_parser("install", help="从 marketplace 安装 Agent（校验完整性后注册）")
    sp.add_argument("agent_id")
    sp.add_argument("--version", default=None, help="指定版本（缺省取最新）")
    sp.add_argument("--market", default=_DEFAULT_MARKET)
    sp.set_defaults(func=_cmd_install)

    sp = sub.add_parser("list", help="列出 marketplace 中已发布的 Agent")
    sp.add_argument("--market", default=_DEFAULT_MARKET)
    sp.set_defaults(func=_cmd_list)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv if argv is not None else sys.argv[1:])
    try:
        return args.func(args)
    except packlib.PackError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
