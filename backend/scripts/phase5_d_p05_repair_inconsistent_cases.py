"""Phase 5 Track D P0.5 Gate 1 — Repair script for existing inconsistent data.

The P0 implementation of ``persist_case`` used an idempotent-skip on
``gap_id`` that silently dropped gaps when LLM placeholder IDs collided
across cases. This produced cases with ``len(gaps) == 0 and len(queries) > 0``
(the "0 Gap + N Query" pathology).

This script:
  1. Lists all inconsistent cases (audit).
  2. For each inconsistent case, deletes the orphan queries so the case
     becomes consistently AUTO_PASS (gaps=0, queries=0). This is the
     conservative repair — we do NOT try to reconstruct the original gaps
     because the LLM output is not recoverable post-hoc.
  3. Also verifies that all child IDs are case-scoped (defensive check).

Run:
    python scripts/phase5_d_p05_repair_inconsistent_cases.py --dry-run
    python scripts/phase5_d_p05_repair_inconsistent_cases.py --apply

Prints a per-case report and a summary. --dry-run is default.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Make backend/ importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models.cdi_case import (
    CDICaseModel,
    DocumentationGapModel,
    ProviderQueryModel,
)
from app.services.cdi_persistence import (
    assert_case_consistent,
    derive_case_state,
    load_case,
)


async def _scan_all_cases() -> list[tuple[str, list[str]]]:
    """Return [(case_id, issues)] for every case in the DB."""
    out: list[tuple[str, list[str]]] = []
    async with AsyncSessionLocal() as db:
        ids = (await db.execute(select(CDICaseModel.id).order_by(CDICaseModel.id))).scalars().all()
        for cid in ids:
            case_model = await load_case(db, cid)
            if case_model is None:
                continue
            issues = assert_case_consistent(case_model)
            out.append((cid, issues))
    return out


async def _repair_case(case_id: str, apply: bool) -> dict:
    """Repair a single case by deleting orphan queries.

    Conservative repair: delete queries whose gap_id does not resolve in
    this case. The case then becomes AUTO_PASS (gaps=0 → queries dropped).
    """
    async with AsyncSessionLocal() as db:
        case_model = await load_case(db, case_id)
        if case_model is None:
            return {"case_id": case_id, "action": "skip", "reason": "not_found"}

        gap_ids = {g.id for g in (getattr(case_model, "gaps_", []) or [])}
        queries = list(getattr(case_model, "queries_", []) or [])
        orphan_queries = [q for q in queries if q.gap_id not in gap_ids]

        if not orphan_queries:
            return {"case_id": case_id, "action": "noop", "reason": "no_orphans"}

        orphan_ids = [q.id for q in orphan_queries]
        if apply:
            for q in orphan_queries:
                await db.delete(q)
            await db.commit()

        return {
            "case_id": case_id,
            "action": "delete_orphan_queries" if apply else "would_delete_orphan_queries",
            "orphan_query_ids": orphan_ids,
            "orphan_count": len(orphan_ids),
            "remaining_queries": len(queries) - len(orphan_queries),
            "remaining_gaps": len(gap_ids),
        }


async def _migrate_legacy_ids(apply: bool) -> list[dict]:
    """Migrate legacy non-case-scoped IDs to case-scoped format.

    For each case with gaps/queries whose IDs don't start with the case_id,
    rename them in-place to ``{case_id}/GAP-NNN`` / ``{case_id}/Q-NNN``.
    Also re-links ProviderQuery.gap_id to the new gap IDs.
    """
    out: list[dict] = []
    async with AsyncSessionLocal() as db:
        ids = (await db.execute(select(CDICaseModel.id).order_by(CDICaseModel.id))).scalars().all()
        for cid in ids:
            case_model = await load_case(db, cid)
            if case_model is None:
                continue
            gaps = list(getattr(case_model, "gaps_", []) or [])
            queries = list(getattr(case_model, "queries_", []) or [])

            gap_id_map: dict[str, str] = {}
            needs_migrate = False
            for idx, g in enumerate(gaps, start=1):
                if g.id and not g.id.startswith(cid):
                    new_id = f"{cid}/GAP-{idx:03d}"
                    gap_id_map[g.id] = new_id
                    needs_migrate = True

            query_id_map: dict[str, str] = {}
            for idx, q in enumerate(queries, start=1):
                if q.id and not q.id.startswith(cid):
                    new_id = f"{cid}/Q-{idx:03d}"
                    query_id_map[q.id] = new_id
                    needs_migrate = True

            if not needs_migrate:
                continue

            entry: dict[str, Any] = {"case_id": cid, "gap_renames": gap_id_map, "query_renames": query_id_map}
            if apply:
                # Apply gap renames
                for old, new in gap_id_map.items():
                    gap_obj = next((g for g in gaps if g.id == old), None)
                    if gap_obj:
                        gap_obj.id = new
                # Apply query renames + update gap_id FK
                for old, new in query_id_map.items():
                    q_obj = next((q for q in queries if q.id == old), None)
                    if q_obj:
                        q_obj.id = new
                        if q_obj.gap_id in gap_id_map:
                            q_obj.gap_id = gap_id_map[q_obj.gap_id]
                await db.commit()
            out.append(entry)
    return out


async def main(apply: bool) -> int:
    print(f"[repair] mode={'APPLY' if apply else 'DRY_RUN'}")
    print()

    issues_by_case = await _scan_all_cases()
    inconsistent = [(cid, iss) for cid, iss in issues_by_case if iss]
    print(f"Total cases:       {len(issues_by_case)}")
    print(f"Inconsistent:      {len(inconsistent)}")
    print()

    if not inconsistent:
        print("[OK] No inconsistencies detected. Nothing to repair.")
        return 0

    print("=== Inconsistent cases ===")
    for cid, iss in inconsistent:
        print(f"  {cid}:")
        for line in iss:
            print(f"    - {line}")
    print()

    print("=== Repair actions ===")
    summary = []
    for cid, _ in inconsistent:
        result = await _repair_case(cid, apply=apply)
        summary.append(result)
        action = result.get("action")
        if action in ("delete_orphan_queries", "would_delete_orphan_queries"):
            print(
                f"  {cid}: {action} orphan_count={result['orphan_count']} "
                f"remaining_gaps={result['remaining_gaps']} "
                f"remaining_queries={result['remaining_queries']}"
            )
        else:
            print(f"  {cid}: {action} ({result.get('reason','')})")
    print()

    # Post-repair audit
    if apply:
        print()
        print("=== Migrating legacy non-case-scoped IDs ===")
        migrations = await _migrate_legacy_ids(apply=True)
        print(f"Migrated {len(migrations)} cases to case-scoped IDs.")
        for m in migrations:
            print(f"  {m['case_id']}: {len(m['gap_renames'])} gaps + {len(m['query_renames'])} queries")

        print()
        post = await _scan_all_cases()
        post_inconsistent = [(cid, iss) for cid, iss in post if iss]
        print(f"Post-repair inconsistent: {len(post_inconsistent)}")
        if post_inconsistent:
            print("[WARN] Some cases remain inconsistent after repair:")
            for cid, iss in post_inconsistent:
                print(f"  {cid}: {iss}")
        else:
            print("[OK] All cases consistent after repair.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Apply repairs (default: dry-run)")
    parser.add_argument("--dry-run", action="store_true", help="Force dry-run")
    args = parser.parse_args()
    apply = args.apply and not args.dry_run
    raise SystemExit(asyncio.run(main(apply)))
