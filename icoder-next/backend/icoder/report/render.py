from __future__ import annotations

import html

from ..runtime.types import RunResult

_SEV_COLOR = {"Critical": "#c0392b", "Moderate": "#b9770e", "Informational": "#7f8c8d"}


def _highlight(text: str, runs: RunResult) -> str:
    spans: list[tuple[int, int, str]] = []
    for c in runs.codes:
        for ev in c.evidences:
            spans.append((ev.start, ev.end, c.code))
    spans.sort(key=lambda s: (s[0], -s[1]))
    out: list[str] = []
    cursor = 0
    for start, end, code in spans:
        if start < cursor:  # overlap — keep it simple (last-write-wins / skip)
            continue
        out.append(html.escape(text[cursor:start]))
        out.append(
            f'<mark class="ev" data-code="{html.escape(code)}" '
            f'title="{html.escape(code)}">{html.escape(text[start:end])}</mark>'
        )
        cursor = end
    out.append(html.escape(text[cursor:]))
    return "".join(out).replace("\n", "<br>")


def _code_row(c) -> str:
    badge = '<span class="hr">高风险</span>' if c.high_risk else ""
    primary = '<span class="pri">主诊断</span>' if c.is_primary else ""
    notes = "".join(
        f'<li><b>{html.escape(n.kind)}</b>: {html.escape(n.text)}</li>' for n in c.notes
    )
    alts = "".join(
        f'<li>{html.escape(a.code)} {html.escape(a.display)} — {html.escape(a.reason)}</li>'
        for a in c.alternatives
    )
    ev = " ".join(
        f'<code>[{e.start},{e.end}) {html.escape(e.text)}</code>' for e in c.evidences
    )
    return f"""
    <tr>
      <td class="mono">{html.escape(c.code)} {primary} {badge}</td>
      <td>{html.escape(c.display)}<br><span class="muted">{html.escape(c.system)} · conf {c.confidence}</span></td>
      <td>{ev or '<span class="muted">—</span>'}</td>
      <td>{('<ul class="notes">' + notes + '</ul>') if notes else ''}
          {('<ul class="alts">' + alts + '</ul>') if alts else ''}</td>
    </tr>"""


def _drg_block(drg) -> str:
    """DRG/DIP route as MDC → ADRG/DRG(severity) → DIP(病种+分值) + 推导 rationale."""
    if drg is None:
        return '<p class="muted">无</p>'
    kind = "外科组" if drg.surgical else "内科组"
    sev = {"MCC": "MCC · 伴严重并发症/合并症",
           "CC": "CC · 伴并发症/合并症"}.get(drg.cc_mcc, "无 CC/MCC")
    pills = (
        (f'<span class="pill">MDC {html.escape(drg.mdc)} · {html.escape(drg.mdc_name or "")}</span>'
         if drg.mdc else "")
        + f'<span class="pill">{kind}</span>'
        + f'<span class="pill">严重度：{html.escape(sev)}</span>'
    )
    lines = [f"<p>{pills}</p>"]
    if drg.adrg or drg.drg:
        lines.append(
            f'<p>ADRG <b>{html.escape(drg.adrg or "-")}</b> → DRG '
            f'<b>{html.escape(drg.drg or "-")}</b> · {html.escape(drg.group_name or "-")}</p>'
        )
    if drg.dip_code:
        lines.append(
            f'<p>DIP 病种：<b>{html.escape(drg.dip_code)}</b> {html.escape(drg.dip_name or "")} '
            f"· 分值 <b>{drg.dip_score}</b></p>"
        )
    rationale = "".join(f"<li>{html.escape(r)}</li>" for r in drg.rationale)
    if rationale:
        lines.append(f'<ol class="rationale">{rationale}</ol>')
    if drg.note:
        lines.append(f'<p class="muted">{html.escape(drg.note)}</p>')
    return "".join(lines)


def render_html(run: RunResult) -> str:
    text = run.redaction.get("text", "")
    codes_rows = "".join(_code_row(c) for c in run.codes) or '<tr><td colspan="4" class="muted">无</td></tr>'
    cand_rows = (
        "".join(_code_row(c) for c in run.candidates)
        or '<tr><td colspan="4" class="muted">无</td></tr>'
    )
    hits = "".join(
        f'<li style="color:{_SEV_COLOR.get(h.severity, "#333")}">'
        f'<b>{html.escape(h.severity)}</b> · {html.escape(h.rule_id)} · {html.escape(h.message)}</li>'
        for h in run.compliance.hits
    ) or '<li class="muted">无命中</li>'
    drg_html = _drg_block(run.drg_route)
    v = run.versions
    gate_state = "通过" if run.compliance.passed else "拦截"
    review = "需人工复核" if run.compliance.human_review_required else "无需复核"
    return f"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<title>编码审核报告 {html.escape(run.run_id)}</title>
<style>
 body{{font-family:Inter,system-ui,"Microsoft YaHei",sans-serif;margin:0;background:#f6f7f8;color:#16181a}}
 .wrap{{max-width:980px;margin:0 auto;padding:24px}}
 h1{{font-size:18px;margin:0 0 4px}} h2{{font-size:14px;margin:22px 0 8px;color:#0f9d8f}}
 .mono,code{{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:12px}}
 .card{{background:#fff;border:1px solid #e6e8ea;border-radius:8px;padding:16px}}
 table{{width:100%;border-collapse:collapse;font-size:13px}}
 td,th{{border-bottom:1px solid #eef0f1;padding:8px;text-align:left;vertical-align:top}}
 .muted{{color:#8a9099}} .ev{{background:#d6f5ef;border-radius:3px;padding:0 2px}}
 .hr{{background:#fdecea;color:#c0392b;font-size:11px;padding:1px 6px;border-radius:10px;margin-left:4px}}
 .pri{{background:#eafaf1;color:#1e8449;font-size:11px;padding:1px 6px;border-radius:10px;margin-left:4px}}
 .notes b,.alts b{{color:#555}} ul{{margin:4px 0;padding-left:18px}}
 .doc{{line-height:1.9;font-size:14px}} .gate{{font-weight:700}}
 .pill{{display:inline-block;background:#eef2f3;border-radius:10px;padding:2px 8px;font-size:12px;margin-right:6px}}
 ol.rationale{{color:#555;font-size:12px}} ol.rationale li{{margin:2px 0}}
 footer{{margin-top:20px;font-size:11px;color:#8a9099}}
</style></head><body><div class="wrap">
 <h1>病案首页编码审核报告</h1>
 <p class="muted mono">{html.escape(run.run_id)} · agent {html.escape(run.agent_id)}@{html.escape(run.agent_version)} · {html.escape(run.coding_system)}</p>
 <p><span class="pill">门禁：<span class="gate">{gate_state}</span></span>
    <span class="pill">{review}</span>
    <span class="pill">写回 EMR：{'已阻断' if run.production_writeback_blocked else '开放'}</span></p>

 <h2>1 · 去标识化病历（证据高亮）</h2>
 <div class="card doc">{_highlight(text, run)}</div>

 <h2>2 · Codes（确信 · 可计费）</h2>
 <div class="card"><table><thead><tr><th>编码</th><th>名称</th><th>证据(char-span)</th><th>注释/鉴别</th></tr></thead>
 <tbody>{codes_rows}</tbody></table></div>

 <h2>3 · Candidates（需复核）</h2>
 <div class="card"><table><thead><tr><th>编码</th><th>名称</th><th>证据</th><th>注释/鉴别</th></tr></thead>
 <tbody>{cand_rows}</tbody></table></div>

 <h2>4 · 合规门禁</h2>
 <div class="card"><ul>{hits}</ul></div>

 <h2>5 · DRG/DIP 分组路由</h2>
 <div class="card">{drg_html}</div>

 <footer>runtime {html.escape(v.runtime_version)} · agent {html.escape(v.agent_version)} ·
  ruleset {html.escape(v.ruleset_version)} · catalog {html.escape(v.catalog_version)} ·
  model {html.escape(v.model_version)}</footer>
</div></body></html>"""
