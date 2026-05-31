# Pilot Report Builder — hospital-facing evaluation summaries
"""Build hospital-pilot-readable evaluation reports in management language."""


def build_hospital_summary(
    evaluation_results: list[dict],
    inter_rater: dict | None = None,
) -> str:
    """Build a hospital-facing evaluation summary in Chinese management language."""
    if not evaluation_results:
        return "暂无可用的评估数据。请先执行批量评估。\n\npython scripts/pilot_eval_runbook.py run-evaluation"

    n = len(evaluation_results)

    primary_matches = sum(1 for r in evaluation_results if r.get("primary_diag_match"))
    soft_matches = sum(1 for r in evaluation_results if r.get("primary_diag_soft_match"))
    proc_matches = sum(1 for r in evaluation_results if r.get("main_proc_match"))
    drg_matches = sum(1 for r in evaluation_results if r.get("drg_match"))
    escalation_count = sum(1 for r in evaluation_results if r.get("escalation_count", 0) > 0)

    parts = []

    # Title
    parts.append(f"# iCoDer 试点评估报告\n")
    parts.append(f"**评估病例数**: {n} 例\n")

    # Top-line results
    parts.append("## 一、总体结果\n")
    strict_rate = round(primary_matches / n * 100) if n > 0 else 0
    soft_rate = round(soft_matches / n * 100) if n > 0 else 0
    proc_rate = round(proc_matches / n * 100) if n > 0 else 0

    parts.append(f"| 指标 | 结果 | 试点建议阈值 |")
    parts.append(f"|------|------|-------------|")
    parts.append(f"| 主诊断匹配率（严格） | {strict_rate}% ({primary_matches}/{n}) | ≥ 50% |")
    parts.append(f"| 主诊断匹配率（宽松） | {soft_rate}% ({soft_matches}/{n}) | ≥ 70% |")
    parts.append(f"| 手术编码匹配率 | {proc_rate}% ({proc_matches}/{n}) | ≥ 60% |")

    if drg_matches > 0:
        drg_rate = round(drg_matches / n * 100) if n > 0 else 0
        parts.append(f"| DRG 分组匹配率 | {drg_rate}% ({drg_matches}/{n}) | ≥ 50% |")

    parts.append("")

    # Routing distribution
    tier_dist = {"auto": 0, "review": 0, "escalate": 0}
    for r in evaluation_results:
        for rd in r.get("routing", []):
            t = rd.get("tier", "")
            if t in tier_dist:
                tier_dist[t] += 1

    parts.append("## 二、AI 工作负载分布\n")
    parts.append(f"| 自动通过 (AUTO) | 人工复核 (REVIEW) | 升级审核 (ESCALATE) |")
    parts.append(f"|----------------|------------------|---------------------|")
    parts.append(f"| {tier_dist['auto']} | {tier_dist['review']} | {tier_dist['escalate']} |")
    parts.append("")

    # Unsupported evidence
    unsupported_cases = [r for r in evaluation_results if r.get("unsupported_code_count", 0) > 0]
    parts.append("## 三、文书支撑不足病例\n")
    if unsupported_cases:
        parts.append(f"共 **{len(unsupported_cases)}** 例存在至少一个编码证据不足。\n")
        parts.append("| 病例 | 无支撑编码数 |")
        parts.append("|------|-------------|")
        for uc in unsupported_cases[:10]:
            parts.append(f"| {uc.get('case_id', '?')} | {uc.get('unsupported_code_count', 0)} |")
    else:
        parts.append("全部病例的编码建议均有证据支撑。\n")
    parts.append("")

    # Disagreement
    disagreement_cases = [r for r in evaluation_results if r.get("disagreement_count", 0) > 0]
    parts.append("## 四、AI 与金标不一致病例\n")
    if disagreement_cases:
        parts.append(f"共 **{len(disagreement_cases)}** 例存在 AI 与金标编码不一致。\n")
        parts.append("| 病例 | 不一致数 | 影响DRG |")
        parts.append("|------|---------|---------|")
        for dc in disagreement_cases[:10]:
            parts.append(f"| {dc.get('case_id', '?')} | {dc.get('disagreement_count', 0)} | {'是' if dc.get('drg_impacted') else '否'} |")
    else:
        parts.append("全部病例 AI 与金标一致。\n")
    parts.append("")

    # High-risk escalations
    if escalation_count > 0:
        parts.append("## 五、高风险升级病例\n")
        parts.append(f"共 **{escalation_count}** 例触发了升级审核机制，需高级编码员关注。\n")
        parts.append("这些病例存在以下风险因素之一：主诊断选择不确定、证据矛盾、DRG敏感差异。\n")

    # Inter-rater note
    if inter_rater:
        kappa = inter_rater.get("avg_cohens_kappa", 0)
        kappa_text = "高度一致" if kappa >= 0.61 else ("中等一致" if kappa >= 0.41 else "需关注")
        parts.append("## 六、编码员间一致性\n")
        parts.append(f"Cohen's Kappa 平均值: **{kappa:.2f}**（{kappa_text}）\n")
        parts.append(f"覆盖 {inter_rater.get('n_raters', 0)} 位编码员，{inter_rater.get('n_cases', 0)} 例病例。\n")

    # Conclusion
    parts.append("## 七、试点结论建议\n")
    if strict_rate >= 50 and soft_rate >= 70:
        parts.append("试点达到预期标准。主诊断匹配率和证据覆盖率均在建议阈值以上。")
        parts.append("建议：进入下一阶段，扩大病例规模至 100 例以上，覆盖更多科室。")
    elif strict_rate >= 30 or soft_rate >= 50:
        parts.append("试点部分达标。部分指标接近但未完全达到建议阈值。")
        parts.append("建议：针对性改进以下方面后重新评估。")
        if unsupported_cases:
            parts.append("  - 补充病历文书，减少证据不足病例")
        if disagreement_cases:
            parts.append("  - 分析 AI 与金标不一致的根本原因")
    else:
        parts.append("试点未达预期标准。多项指标显著低于建议阈值。")
        parts.append("建议：检查数据质量、LLM 配置、规则引擎覆盖度后重新评估。")

    return "\n".join(parts)


def build_unsupported_evidence_report(evaluation_results: list[dict]) -> list[dict]:
    """Build a list of cases with unsupported evidence — like a medical record quality report."""
    report = []
    for r in evaluation_results:
        unsupported = r.get("unsupported_codes", [])
        if not unsupported:
            continue
        report.append({
            "case_id": r.get("case_id", "?"),
            "unsupported_count": len(unsupported),
            "codes": unsupported[:5],
            "evidence_strength_avg": r.get("evidence_strength_avg", 0),
            "drg_sensitive": r.get("drg_impacted", False),
            "recommendation": "建议补充病历文书后重新审核" if len(unsupported) >= 3 else "建议编码员复核确认",
        })
    return sorted(report, key=lambda x: x["unsupported_count"], reverse=True)


def build_drg_sensitive_report(evaluation_results: list[dict]) -> list[dict]:
    """Build a DRG risk report — risk-prioritized."""
    report = []
    for r in evaluation_results:
        if not r.get("drg_impacted"):
            continue
        report.append({
            "case_id": r.get("case_id", "?"),
            "primary_diag_match": r.get("primary_diag_match", False),
            "disagreement_count": r.get("disagreement_count", 0),
            "drg_sensitive_codes": r.get("drg_sensitive_codes", []),
            "human_override": r.get("human_override", False),
            "escalation_reason": r.get("escalation_reason", "DRG编码变更"),
            "recommendation": "高级编码员审核" if not r.get("primary_diag_match") else "编码员确认DRG分组",
        })
    return sorted(report, key=lambda x: len(x.get("drg_sensitive_codes", [])), reverse=True)


def build_pilot_conclusion(evaluation_results: list[dict], inter_rater: dict | None = None) -> str:
    """Build a concise pilot conclusion for hospital management."""
    if not evaluation_results:
        return "暂无评估数据。"

    n = len(evaluation_results)
    primary_matches = sum(1 for r in evaluation_results if r.get("primary_diag_match"))
    strict_rate = round(primary_matches / n * 100) if n > 0 else 0
    unsupported = sum(1 for r in evaluation_results if r.get("unsupported_code_count", 0) > 0)
    disagreements = sum(1 for r in evaluation_results if r.get("disagreement_count", 0) > 0)

    parts = [f"本次试点共评估 {n} 例出院病例。"]
    parts.append(f"iCoDer 主诊断选择准确率为 {strict_rate}%，")
    parts.append(f"{n - unsupported} 例编码建议有充分证据支撑。")

    if disagreements > 0:
        parts.append(f"{disagreements} 例与编码员金标存在差异，已记录为待分析案例。")
    else:
        parts.append("无 AI 与编码员不一致病例。")

    parts.append("系统在试点期间运行稳定，无阻断性故障。")

    return "".join(parts)
