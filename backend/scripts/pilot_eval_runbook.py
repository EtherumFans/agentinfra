#!/usr/bin/env python3
"""Pilot Evaluation Runbook CLI — iCoDer 试点评估操作手册

Commands:
    generate-template    生成金标病例填写模板
    validate-gold        校验金标病例文件（dry-run）
    import-gold          导入金标病例文件
    run-evaluation       批量运行评估
    export-report        导出评估报告
"""
import argparse
import json
import sys
from pathlib import Path

# Ensure backend is on path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def cmd_generate_template(args):
    """生成金标病例模板."""
    from app.services.gold_case_template import generate_gold_case_template

    print("=" * 60)
    print("  金标病例模板生成")
    print("=" * 60)

    fmt = getattr(args, "format", "json")
    department = getattr(args, "department", "")
    template = generate_gold_case_template(department=department, output_format=fmt)

    output = getattr(args, "output", None)
    if output:
        if fmt == "markdown":
            Path(output).write_text(template, encoding="utf-8")
        else:
            Path(output).write_text(json.dumps(template, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"✅ 模板已保存到: {output}")
    else:
        if fmt == "markdown":
            print(template)
        else:
            print(json.dumps(template, ensure_ascii=False, indent=2))

    print(f"科室: {department or '(未指定 — 请在模板中填写)'}")
    print(f"格式: {fmt}")
    print("下一步: 将模板分发给编码员填写 → validate-gold")


def cmd_validate_gold(args):
    """校验金标病例文件."""
    from app.services.gold_case_importer import import_gold_cases_from_file

    print("=" * 60)
    print("  金标病例校验 (Dry-Run)")
    print("=" * 60)

    filepath = args.file
    fmt = args.format or _detect_format(filepath)

    print(f"文件: {filepath}")
    print(f"格式: {fmt}")
    print()

    try:
        result = import_gold_cases_from_file(filepath, file_format=fmt, mode="validation_only")
    except FileNotFoundError:
        print(f"❌ 文件不存在: {filepath}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 解析失败: {e}")
        sys.exit(1)

    print(f"总行数: {result['total_rows']}")
    print(f"错误:   {result['errors']}")
    print(f"警告:   {result['warnings']}")
    print()

    # Print row-level details
    for row in result["row_results"]:
        status_icon = {"ok": "✅", "warning": "⚠️", "error": "❌", "skipped": "⏭️"}.get(row["status"], "❓")
        print(f"  {status_icon} 行{row['row_index']:03d} [{row['encounter_id']}] — {row['status']}")
        for e in row.get("errors", []):
            print(f"     错误: {e}")
        for w in row.get("warnings", []):
            print(f"     警告: {w}")

    if result["errors"] > 0:
        print(f"\n❌ 发现 {result['errors']} 个错误，请修正后重新校验。")
        sys.exit(1)
    elif result["warnings"] > 0:
        print(f"\n⚠️ 校验通过但有 {result['warnings']} 个警告。可以用 --mode import 导入。")
    else:
        print("\n✅ 全部通过！可以执行 import-gold 导入。")


def cmd_import_gold(args):
    """导入金标病例文件."""
    from app.services.gold_case_importer import import_gold_cases_from_file

    print("=" * 60)
    print("  金标病例导入")
    print("=" * 60)

    filepath = args.file
    fmt = args.format or _detect_format(filepath)
    dry_run = getattr(args, "dry_run", False)
    upsert = getattr(args, "upsert", False)
    mode = "dry_run" if dry_run else "import"

    print(f"文件:   {filepath}")
    print(f"格式:   {fmt}")
    print(f"模式:   {mode}")
    print(f"Upsert: {upsert}")
    print()

    try:
        result = import_gold_cases_from_file(filepath, file_format=fmt, mode=mode, upsert=upsert)
    except FileNotFoundError:
        print(f"❌ 文件不存在: {filepath}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 导入失败: {e}")
        sys.exit(1)

    print(f"总行数:   {result['total_rows']}")
    print(f"已导入:   {result['imported']}")
    print(f"已跳过:   {result['skipped']}")
    print(f"错误:     {result['errors']}")
    print(f"警告:     {result['warnings']}")
    print(f"需仲裁:   {len(result.get('adjudication_needed', []))}")

    if result.get("adjudication_needed"):
        print("\n⚠️ 以下病例需要仲裁：")
        for adj in result["adjudication_needed"]:
            print(f"  {adj['encounter_id']}: {adj['reviewer1']}={adj['reviewer1_code']} vs {adj['reviewer2']}={adj['reviewer2_code']}")

    if result["errors"] > 0:
        print(f"\n❌ 导入失败：{result['errors']} 个错误。")
        sys.exit(1)
    elif dry_run:
        print("\n✅ Dry-run 通过。使用不带 --dry-run 的导入命令正式执行。")
    else:
        print(f"\n✅ 成功导入 {result['imported']} 条金标病例。下一步: run-evaluation")


def cmd_run_evaluation(args):
    """运行批量评估."""
    import asyncio

    print("=" * 60)
    print("  批量评估运行")
    print("=" * 60)

    async def _run():
        from app.database import async_session_factory
        from app.models.gold_case import GoldCase
        from app.agents.orchestrator import agent_orchestrator
        from sqlalchemy import select

        async with async_session_factory() as db:
            query = select(GoldCase)
            result = await db.execute(query)
            cases = result.scalars().all()

            if not cases:
                print("❌ 未找到金标病例。请先执行 import-gold。")
                sys.exit(1)

            print(f"金标病例数: {len(cases)}")
            per_case = []
            primary_matches = 0
            total = 0

            for gc in cases:
                if not gc.full_case_data:
                    print(f"  ⏭️ {gc.case_id}: 缺少 full_case_data，跳过")
                    continue

                print(f"  🔄 {gc.case_id}...")
                try:
                    pipeline_result = await agent_orchestrator.run_pipeline(gc.full_case_data)
                except Exception as e:
                    print(f"    ❌ Pipeline 失败: {e}")
                    continue

                agent_pd = pipeline_result.get("primary_diagnosis", {}).get("code", "")
                match = agent_pd == gc.expected_principal_diagnosis
                if match:
                    primary_matches += 1
                total += 1

                report = pipeline_result.get("case_reasoning_report", {})
                reasoning_score = sum(1 for s in ("case_overview", "clinical_timeline", "evidence_assessment",
                                                   "principal_diagnosis", "disagreement_analysis", "confidence_routing")
                                      if report.get(s)) / 6.0

                per_case.append({
                    "case_id": gc.case_id,
                    "primary_diag_match": match,
                    "agent_pd": agent_pd,
                    "gold_pd": gc.expected_principal_diagnosis,
                    "reasoning_score": round(reasoning_score, 2),
                })
                icon = "✅" if match else "❌"
                print(f"    {icon} 主诊断: AI={agent_pd} vs Gold={gc.expected_principal_diagnosis}")

            accuracy = primary_matches / total if total > 0 else 0
            summary = {
                "total_evaluated": total,
                "primary_diag_accuracy": round(accuracy, 2),
                "per_case": per_case,
            }

            output = getattr(args, "output", None)
            if output:
                Path(output).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"\n📄 评估结果已保存到: {output}")

            print(f"\n{'=' * 60}")
            print(f"评估完成: {total} 例, 主诊断准确率 {accuracy:.0%}")
            print(f"{'=' * 60}")

    asyncio.run(_run())


def cmd_export_report(args):
    """导出评估报告."""
    print("=" * 60)
    print("  评估报告导出")
    print("=" * 60)

    output = getattr(args, "output", "pilot_evaluation_report.json")
    fmt = getattr(args, "format", "json")

    report = {
        "pilot_name": getattr(args, "pilot_name", "iCoDer 试点评估"),
        "generated_at": "",
        "sections": {
            "gold_case_summary": "执行 import-gold 获取",
            "evaluation_metrics": "执行 run-evaluation 获取",
            "inter_rater_agreement": "执行 inter-rater 计算获取",
            "case_reasoning_reports": "每例 CaseReasoningReport",
            "known_limitations": "参考 docs/PILOT_KNOWN_LIMITATIONS.md",
            "acceptance_checklist": "参考 docs/PILOT_ACCEPTANCE_CHECKLIST.md",
        },
        "_instructions": "本报告由 pilot_eval_runbook.py 生成。各 section 需通过对应命令填充。",
    }

    import datetime
    report["generated_at"] = datetime.datetime.utcnow().isoformat()

    if fmt == "json":
        content = json.dumps(report, ensure_ascii=False, indent=2)
    else:
        content = json.dumps(report, ensure_ascii=False, indent=2)

    Path(output).write_text(content, encoding="utf-8")
    print(f"✅ 报告框架已导出到: {output}")
    print("下一步: 运行 run-evaluation 后，将结果填入各 section。")


def _detect_format(filepath: str) -> str:
    if filepath.endswith(".csv"):
        return "csv"
    return "json"


def main():
    parser = argparse.ArgumentParser(description="iCoDer 试点评估操作手册 CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    # generate-template
    p = sub.add_parser("generate-template", help="生成金标病例模板")
    p.add_argument("--department", default="", help="科室名称")
    p.add_argument("--format", default="json", choices=["json", "markdown"], help="输出格式")
    p.add_argument("--output", help="输出文件路径")

    # validate-gold
    p = sub.add_parser("validate-gold", help="校验金标病例文件")
    p.add_argument("file", help="金标文件路径 (.json/.csv)")
    p.add_argument("--format", choices=["json", "csv"], help="文件格式（默认根据扩展名推断）")

    # import-gold
    p = sub.add_parser("import-gold", help="导入金标病例")
    p.add_argument("file", help="金标文件路径")
    p.add_argument("--format", choices=["json", "csv"], help="文件格式")
    p.add_argument("--dry-run", action="store_true", help="只校验不导入")
    p.add_argument("--upsert", action="store_true", help="更新已存在的记录")

    # run-evaluation
    p = sub.add_parser("run-evaluation", help="批量运行评估")
    p.add_argument("--output", help="评估结果输出文件")

    # export-report
    p = sub.add_parser("export-report", help="导出评估报告框架")
    p.add_argument("--output", default="pilot_evaluation_report.json", help="输出文件")
    p.add_argument("--format", default="json", choices=["json"], help="输出格式")
    p.add_argument("--pilot_name", default="iCoDer 试点评估", help="试点名称")

    args = parser.parse_args()

    commands = {
        "generate-template": cmd_generate_template,
        "validate-gold": cmd_validate_gold,
        "import-gold": cmd_import_gold,
        "run-evaluation": cmd_run_evaluation,
        "export-report": cmd_export_report,
    }

    commands[args.command](args)


if __name__ == "__main__":
    main()
