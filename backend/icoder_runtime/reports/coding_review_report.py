"""iCoDer M3-0 — 病案首页编码审核报告生成器 (HTML, 18 节, 含 pipeline validation disclaimer).

Agent: icoder/medcoder-coding-review-agent@1.0.0
Positioning: 这是 iCoDer 基础设施上的第一个官方样板 Agent 的报告, 不是 iCoDer 全部产品定位.

**Output**: 纯 HTML (M3-0 阶段) — PDF 留 M3+ 阶段.

**18 节内容** (M3 任务 §10):
1. Agent 名称与版本
2. Run ID / Trace ID
3. 运行时间
4. 输入来源
5. prediction_mode (link_validation / model_evaluation)
6. 模型版本
7. 码表版本
8. 规则版本
9. 主诊断审核结果
10. 其他诊断审核结果
11. 手术操作审核结果
12. 高风险易错编码点
13. 证据回链
14. 人工复核记录
15. 风险路由结果
16. 医学安全门禁结果
17. 审计日志摘要
18. 免责声明

**Disclaimer (硬性)**:
- pipeline validation 模式: 报告顶部 banner + §18 必含
- 不声称模型效果
- 不暗示可生产写回或医保上传
"""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Phase D3 (2026-06-26): pull canonical constants from the SSOT — the
# legacy ``homepage-coding-review`` 14-stage shim has been removed.
from icoder_runtime.constants.coding_review_constants import (
    AGENT_REF,
    PIPELINE_STAGES,
    PRIORITY_HIGH_RISK_CODES,
    PIPELINE_VALIDATION_DISCLAIMER,
)


def _esc(s: Any) -> str:
    return html.escape(str(s)) if s is not None else ""


def _section(title: str, body: str, anchor: str | None = None) -> str:
    """Render a report section. anchor 可选 — 用于 TOC 跳转 (M3-0.2 P6)."""
    anchor_html = f' id="{_esc(anchor)}"' if anchor else ""
    return f"""
<section class="report-section"{anchor_html}>
  <h2>{_esc(title)}</h2>
  <div class="section-body">{body}</div>
</section>
"""


# 报告固定 18 节目录 (M3-0.2 P6) — 用于生成 TOC 和 anchor.
# 任何 report 必须涵盖的最小集, 缺节会被视为报告不完整.
REPORT_SECTIONS: list[tuple[str, str]] = [
    ("§1",   "section-1-agent"),
    ("§2",   "section-2-run"),
    ("§3",   "section-3-time"),
    ("§4",   "section-4-input"),
    ("§5",   "section-5-mode"),
    ("§6-8", "section-6-8-versions"),
    ("§6.5", "section-65-drg"),
    ("§9",   "section-9-primary-dx"),
    ("§10",  "section-10-other-dx"),
    ("§11",  "section-11-procedures"),
    ("§12",  "section-12-high-risk"),
    ("§13",  "section-13-evidence"),
    ("§14",  "section-14-human-review"),
    ("§15",  "section-15-risk-route"),
    ("§16",  "section-16-safety-gate"),
    ("§17",  "section-17-audit"),
    ("附",    "section-appendix-14-stages"),
    ("§18",  "section-18-disclaimer"),
]


def _render_toc() -> str:
    """渲染报告固定 18 节目录 (M3-0.2 P6).
    作用:
    1. 审阅者一眼能看到全报告骨架 (Clinical Precision — 透明可审)
    2. anchor 跳转, 院长 / 编码员可以快速定位到任何一节
    3. 验收方/合规可机器解析 (TOC 结构固定)
    """
    items = []
    for label, anchor in REPORT_SECTIONS:
        items.append(
            f'<li><a href="#{anchor}" class="toc-link">{_esc(label)}</a></li>'
        )
    return f"""
<nav class="report-toc" aria-label="报告目录">
  <div class="toc-header">报告目录 (18 节)</div>
  <ol class="toc-list">
    {''.join(items)}
  </ol>
</nav>
"""


def _table(rows: list[dict], columns: list[tuple[str, str]]) -> str:
    """rows: list[dict]; columns: list[(key, label)]"""
    head = "".join(f"<th>{_esc(label)}</th>" for _, label in columns)
    body_rows = []
    for r in rows:
        cells = "".join(f"<td>{_esc(r.get(k, ''))}</td>" for k, _ in columns)
        body_rows.append(f"<tr>{cells}</tr>")
    return f"""
<table class="report-table">
  <thead><tr>{head}</tr></thead>
  <tbody>{''.join(body_rows)}</tbody>
</table>
"""


def _render_codes_table(items: list[dict], role_label: str) -> str:
    if not items:
        return f"<p class='muted'>(无 {role_label})</p>"
    rows = []
    for it in items:
        rows.append({
            "code": it.get("code", ""),
            "name": it.get("description", it.get("name", "")),
            "role": role_label,
            "confidence": it.get("confidence", ""),
            "evidence_count": len(it.get("evidence", [])) if isinstance(it.get("evidence"), list) else 0,
            "human_review_required": it.get("human_review_required", False),
            "risk_level": it.get("risk_level", ""),
        })
    return _table(rows, [
        ("code", "编码"), ("name", "名称"), ("role", "角色"),
        ("confidence", "置信度"), ("evidence_count", "证据数"),
        ("human_review_required", "人工复核"), ("risk_level", "风险等级"),
    ])


def _render_high_risk(items: list[dict]) -> str:
    if not items:
        return "<p class='muted'>(未触发高风险易错编码点)</p>"
    rows = []
    for it in items:
        rows.append({
            "code": it.get("code", ""),
            "is_priority": "**PRIORITY**" if it.get("code") in PRIORITY_HIGH_RISK_CODES else "—",
            "reason": it.get("reason", ""),
            "evidence_count": len(it.get("evidence", [])) if isinstance(it.get("evidence"), list) else 0,
            "human_review_required": it.get("human_review_required", True),
            "current_status": it.get("current_status", "pending"),
        })
    return _table(rows, [
        ("code", "编码"), ("is_priority", "是否重点"),
        ("reason", "触发原因"), ("evidence_count", "证据数"),
        ("human_review_required", "需人工复核"),
        ("current_status", "当前状态"),
    ])


def _render_evidence_chain(items: list[dict]) -> str:
    if not items:
        return "<p class='muted'>(无证据回链)</p>"
    rows = []
    for it in items:
        rows.append({
            "field": it.get("source_field", ""),
            "text": (it.get("source_text", "")[:60] + "…") if len(it.get("source_text", "")) > 60 else it.get("source_text", ""),
            "match_method": it.get("match_method", ""),
            "confidence": it.get("confidence", ""),
            "is_gold": it.get("is_gold_evidence", False),
            "source": it.get("source", "auto_bootstrap"),
        })
    return _table(rows, [
        ("field", "来源字段"), ("text", "证据文本"),
        ("match_method", "匹配方法"), ("confidence", "置信度"),
        ("is_gold", "人工 gold"), ("source", "数据源"),
    ])


def _render_human_review(records: list[dict]) -> str:
    if not records:
        return "<p class='muted'>(暂无人工复核记录)</p>"
    rows = []
    for r in records:
        rows.append({
            "reviewer": r.get("reviewer", ""),
            "role": r.get("reviewer_role", "(未填)"),
            "action": r.get("action", ""),
            "target_code": r.get("target_code", ""),
            "new_code": r.get("new_code", ""),
            "reason_code": r.get("reason_code", ""),
            "review_note": (r.get("review_note", "")[:80] + "…") if len(r.get("review_note", "")) > 80 else r.get("review_note", ""),
            "confirmed_at": r.get("confirmed_at", ""),
        })
    return _table(rows, [
        ("reviewer", "审核人"), ("role", "角色"),
        ("action", "动作"), ("target_code", "原编码"),
        ("new_code", "修改后"), ("reason_code", "原因码"),
        ("review_note", "备注"), ("confirmed_at", "时间"),
    ])


def _render_risk_route(rr: dict) -> str:
    if not rr:
        return "<p class='muted'>(无风险路由)</p>"
    return f"""
<dl class="kv">
  <dt>风险等级</dt><dd><span class="risk risk-{_esc(rr.get('level', 'unknown'))}">{_esc(rr.get('level', 'unknown'))}</span></dd>
  <dt>原因</dt><dd>{_esc('; '.join(rr.get('reasons', [])))}</dd>
  <dt>样本被拒</dt><dd>{_esc(rr.get('sample_rejected', False))}</dd>
  <dt>高风险码命中</dt><dd>{_esc(', '.join(rr.get('high_risk_hits', [])))}</dd>
</dl>
"""


def _render_safety_gate(sg: dict) -> str:
    if not sg:
        return "<p class='muted'>(无安全门禁记录)</p>"
    rules = sg.get("rules", [])
    if not rules:
        return f"""
<dl class="kv">
  <dt>规则数</dt><dd>{_esc(sg.get('rule_count', 0))}</dd>
  <dt>block 数</dt><dd>{_esc(sg.get('block_count', 0))}</dd>
</dl>
"""
    rows = [{"rule": r.get("rule", ""), "status": r.get("status", ""), "reason": r.get("reason", "")} for r in rules]
    return _table(rows, [("rule", "规则"), ("status", "状态"), ("reason", "原因")])


def _render_audit_log(audit: list[dict]) -> str:
    if not audit:
        return "<p class='muted'>(无审计日志)</p>"
    rows = []
    for a in audit:
        rows.append({
            "actor": a.get("actor", ""),
            "action": a.get("action", ""),
            "target": a.get("target", ""),
            "at": a.get("at", ""),
        })
    return _table(rows, [("actor", "操作者"), ("action", "动作"), ("target", "对象"), ("at", "时间")])


def _render_disclaimer(mode: str) -> str:
    """§18 免责声明 (M3-0 硬性)."""
    if mode == "link_validation":
        return f"""
<div class="disclaimer link-validation">
  <p><strong>⚠️ Pipeline Validation 模式</strong></p>
  <p>{_esc(PIPELINE_VALIDATION_DISCLAIMER)}</p>
</div>
"""
    return """
<div class="disclaimer model-evaluation">
  <p><strong>模型评估模式 (M3 阶段)</strong></p>
  <p>本报告由 external prediction-file 驱动, P/R/F1 等指标需在 M3 后续阶段实测, M3-0 阶段不启用.</p>
</div>
"""


def render_report(
    *,
    run_id: str,
    trace_id: str,
    input_source: str,
    prediction_mode: str = "link_validation",
    model_version: str = "unknown",
    code_dict_version: str = "unknown",
    rule_version: str = "unknown",
    primary_diagnosis: dict | None = None,
    secondary_diagnoses: list[dict] | None = None,
    procedures: list[dict] | None = None,
    high_risk_coding_points: list[dict] | None = None,
    evidence_chain: list[dict] | None = None,
    human_review_records: list[dict] | None = None,
    risk_route: dict | None = None,
    safety_gate: dict | None = None,
    drg_route: dict | None = None,
    audit_log: list[dict] | None = None,
    pipeline_stages_observed: list[str] | None = None,
    started_at: str = "",
    finished_at: str = "",
) -> str:
    """生成 18 节 HTML 报告。

    Args:
        prediction_mode: "link_validation" (M3-0 默认) / "model_evaluation" (M3+)
        model_version / code_dict_version / rule_version: 硬性显示, 缺失则显 "unknown"
        pipeline_stages_observed: 14 阶段中实际执行的, 用于和 PIPELINE_STAGES 对比
    """
    started_at = started_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    finished_at = finished_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    observed = set(pipeline_stages_observed or [])
    stage_rows = []
    for s in PIPELINE_STAGES:
        stage_rows.append({
            "stage": s,
            "executed": "✅" if s in observed else "—",
            "skipped": "⏭" if s not in observed else "",
        })
    stage_table = _table(stage_rows, [("stage", "阶段"), ("executed", "已执行"), ("skipped", "跳过")])

    body = []
    # §1
    body.append(_section("1. Agent 名称与版本", f"""
<dl class="kv">
  <dt>Agent ref</dt><dd><code>{_esc(AGENT_REF)}</code></dd>
  <dt>Category</dt><dd>medical-coding</dd>
  <dt>Subcategory</dt><dd>medcoder-coding-review</dd>
  <dt>Positioning</dt><dd>本 Agent 是 iCoDer 基础设施上的第一个官方样板 Agent, 不代表 iCoDer 全部产品定位</dd>
</dl>
""", anchor="section-1-agent"))
    # §2
    body.append(_section("2. Run ID / Trace ID", f"""
<dl class="kv">
  <dt>Run ID</dt><dd><code>{_esc(run_id)}</code></dd>
  <dt>Trace ID</dt><dd><code>{_esc(trace_id)}</code></dd>
  <dt>Run Trace URL</dt><dd><code>/api/m2a/runs/{_esc(run_id)}</code></dd>
</dl>
""", anchor="section-2-run"))
    # §3
    body.append(_section("3. 运行时间", f"""
<dl class="kv">
  <dt>Started</dt><dd>{_esc(started_at)}</dd>
  <dt>Finished</dt><dd>{_esc(finished_at)}</dd>
</dl>
""", anchor="section-3-time"))
    # §4
    body.append(_section("4. 输入来源", f"<p>{_esc(input_source)}</p>", anchor="section-4-input"))
    # §5
    body.append(_section("5. prediction_mode", f"""
<dl class="kv">
  <dt>模式</dt><dd><span class="mode mode-{_esc(prediction_mode)}">{_esc(prediction_mode)}</span></dd>
  <dt>说明</dt><dd>{_esc('prediction = gold_evidence, 仅验证技术链路 (M3-0 默认)' if prediction_mode == 'link_validation' else 'external prediction-file 驱动 (M3+ 阶段)')}</dd>
</dl>
""", anchor="section-5-mode"))
    # §6 / §7 / §8
    body.append(_section("6. 模型版本 / 7. 码表版本 / 8. 规则版本", f"""
<dl class="kv">
  <dt>模型版本</dt><dd>{_esc(model_version)}</dd>
  <dt>码表版本</dt><dd>{_esc(code_dict_version)}</dd>
  <dt>规则版本</dt><dd>{_esc(rule_version)}</dd>
</dl>
<p class="muted">注: 缺失时显示 "unknown" — 实际生产部署前必须明确版本号.</p>
""", anchor="section-6-8-versions"))
    # §6.5 — DRG 分组结果 (M3-0 Commit 7)
    if drg_route:
        drg_rows = [
            {"k": "MDC", "v": drg_route.get("mdc", "")},
            {"k": "MDC 名称", "v": drg_route.get("mdc_name", "")},
            {"k": "ADRG", "v": drg_route.get("adrg", "")},
            {"k": "DRG", "v": drg_route.get("drg", "")},
            {"k": "DRG 名称", "v": drg_route.get("drg_name", "")},
            {"k": "CC/MCC 等级", "v": drg_route.get("cc_level", "")},
            {"k": "分组方法", "v": drg_route.get("is_medical_or_surgical") or drg_route.get("grouping_method", "")},
            {"k": "覆盖率 (CHS-DRG 1.1)", "v": "✅" if drg_route.get("coverage") else "❌"},
            {"k": "说明", "v": drg_route.get("reason", "")},
        ]
        drg_table = _table(drg_rows, [("k", "字段"), ("v", "值")])
        body.append(_section("6.5. DRG 分组结果", drg_table, anchor="section-65-drg"))
    else:
        body.append(_section("6.5. DRG 分组结果", "<p class=\"muted\">未触发分组 (无主诊断或主手术)</p>", anchor="section-65-drg"))
    # §9
    body.append(_section("9. 主诊断审核结果", _render_codes_table([primary_diagnosis] if primary_diagnosis else [], "primary_disease"), anchor="section-9-primary-dx"))
    # §10
    body.append(_section("10. 其他诊断审核结果", _render_codes_table(secondary_diagnoses or [], "other_disease"), anchor="section-10-other-dx"))
    # §11
    body.append(_section("11. 手术操作审核结果", _render_codes_table(procedures or [], "primary_surgery/other_surgery"), anchor="section-11-procedures"))
    # §12
    body.append(_section("12. 高风险易错编码点", _render_high_risk(high_risk_coding_points or []), anchor="section-12-high-risk"))
    # §13
    body.append(_section("13. 证据回链", _render_evidence_chain(evidence_chain or []), anchor="section-13-evidence"))
    # §14
    body.append(_section("14. 人工复核记录", _render_human_review(human_review_records or []), anchor="section-14-human-review"))
    # §15
    body.append(_section("15. 风险路由结果", _render_risk_route(risk_route or {}), anchor="section-15-risk-route"))
    # §16
    body.append(_section("16. 医学安全门禁结果", _render_safety_gate(safety_gate or {}), anchor="section-16-safety-gate"))
    # §17
    body.append(_section("17. 审计日志摘要", _render_audit_log(audit_log or []), anchor="section-17-audit"))
    # 附: 14 阶段 Run Trace
    body.append(_section("附: 14 阶段工具调用覆盖", stage_table, anchor="section-appendix-14-stages"))
    # §18 — Disclaimer 永远为最后一节, 不可条件隐藏 (M3-0.2 P6 硬性).
    body.append(_section("18. 免责声明", _render_disclaimer(prediction_mode), anchor="section-18-disclaimer"))

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <title>病案首页编码审核报告 — {_esc(AGENT_REF)}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            max-width: 1080px; margin: 2rem auto; padding: 0 1.5rem; color: #1d1d1f; line-height: 1.55; }}
    h1 {{ font-weight: 600; font-size: 1.8rem; border-bottom: 2px solid #d2d2d7; padding-bottom: 0.5rem; }}
    h2 {{ font-weight: 500; font-size: 1.2rem; margin-top: 2rem; color: #424245;
          border-left: 3px solid #0071e3; padding-left: 0.6rem; }}
    .muted {{ color: #86868b; font-size: 0.9rem; }}
    .report-section {{ margin-bottom: 1.5rem; }}
    .report-table {{ width: 100%; border-collapse: collapse; margin: 0.5rem 0; font-size: 0.9rem; }}
    .report-table th, .report-table td {{ border: 1px solid #d2d2d7; padding: 0.4rem 0.6rem; text-align: left; }}
    .report-table th {{ background: #f5f5f7; font-weight: 500; }}
    .kv {{ display: grid; grid-template-columns: 160px 1fr; gap: 0.3rem 1rem; font-size: 0.9rem; }}
    .kv dt {{ color: #6e6e73; font-weight: 500; }}
    .kv dd {{ margin: 0; }}
    code {{ background: #f5f5f7; padding: 0.1rem 0.3rem; border-radius: 3px; font-size: 0.85em; }}
    .risk {{ padding: 0.1rem 0.4rem; border-radius: 3px; font-weight: 500; }}
    .risk-low {{ background: #d1f4d8; color: #166534; }}
    .risk-medium {{ background: #fef3c7; color: #92400e; }}
    .risk-high {{ background: #fed7aa; color: #9a3412; }}
    .risk-critical {{ background: #fecaca; color: #991b1b; }}
    .risk-unknown {{ background: #e5e7eb; color: #4b5563; }}
    .mode {{ padding: 0.1rem 0.4rem; border-radius: 3px; font-weight: 500; }}
    .mode-link_validation {{ background: #dbeafe; color: #1e40af; }}
    .mode-model_evaluation {{ background: #fae8ff; color: #86198f; }}
    .disclaimer {{ background: #fffbeb; border: 1px solid #fcd34d; border-radius: 6px;
                   padding: 1rem 1.2rem; margin-top: 1rem; }}
    .disclaimer.model-evaluation {{ background: #faf5ff; border-color: #d8b4fe; }}
    .disclaimer strong {{ color: #92400e; }}
    .disclaimer.model-evaluation strong {{ color: #86198f; }}
    /* 报告目录 (M3-0.2 P6) — Clinical Precision: 简洁、克制、不喧宾夺主. */
    .report-toc {{ background: #f5f5f7; border: 1px solid #d2d2d7; border-radius: 6px;
                   padding: 0.8rem 1.2rem; margin: 1rem 0 1.5rem; }}
    .toc-header {{ font-size: 0.85rem; font-weight: 600; color: #424245;
                   margin-bottom: 0.4rem; }}
    .toc-list {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
                 gap: 0.2rem 0.6rem; font-size: 0.85rem; padding: 0; margin: 0;
                 list-style: none; counter-reset: toc; }}
    .toc-list li {{ padding: 0; }}
    .toc-link {{ color: #1d1d1f; text-decoration: none; padding: 0.15rem 0.3rem;
                 display: inline-block; border-radius: 3px; }}
    .toc-link:hover {{ background: #e5e5ea; color: #0071e3; }}
    /* §18 disclaimer 永远固定可见 (M3-0.2 P6 红线) — 加更强的视觉强调. */
    #section-18-disclaimer {{ scroll-margin-top: 1rem; }}
    #section-18-disclaimer .disclaimer {{ border-width: 2px; box-shadow: 0 0 0 1px #fffbeb; }}
  </style>
</head>
<body>
  <h1>病案首页编码审核报告</h1>
  <p class="muted">Generated by {_esc(AGENT_REF)} at {_esc(finished_at)}</p>
  {_render_toc()}
  {''.join(body)}
</body>
</html>
"""


def report_filename(run_id: str, ext: str = "html") -> str:
    return f"coding_review_report_{run_id}.{ext}"


def write_report(report_html: str, output_dir: Path) -> Path:
    """写报告到 output_dir, 返回写入的 Path (M3-0 仅 HTML)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    # 注意: run_id 中可能含特殊字符, 这里以时间戳为文件名 + run_id 末 12 位
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    out_path = output_dir / f"coding_review_report_{timestamp}.html"
    out_path.write_text(report_html, encoding="utf-8")
    return out_path
