/*
 * <icoder-embedded> — on-prem embeddable coding-review widget.
 *
 * This is iCoDer's analog of Corti's <corti-embedded> Web Component, but inverted to
 * private hospital deployment: the host app owns auth/branding and injects a short-lived
 * token via JS (the widget never owns or stores credentials — stateless token), and the
 * baseURL points at the in-hospital iCoDer server (data 不出院).
 *
 * Lifecycle (host-driven, mirrors Corti):  ready -> auth -> configure -> show
 * Event bus: every signal is a single bubbling/composed `embedded-event` CustomEvent whose
 * detail is { type, payload }. Types:
 *   ready | auth | configured | run.started | run.completed | error.triggered
 *   evidence-clicked | code-overridden | rule-gate-triggered | human-review-submitted
 *
 * Usage:
 *   const el = document.querySelector('icoder-embedded');   // base-url set via attribute
 *   el.addEventListener('embedded-event', e => { ... });
 *   el.configureSession({ token: 'demo:coder' });           // auth (host-injected)
 *   el.configure({ agentId: 'icoder/homepage-coding-review-agent', codingSystem: 'ICD-10-CN' });
 *   el.run(text);                                            // -> renders codes + evidence + gate
 */
(function () {
  "use strict";

  const TEAL = "#0f9d8f";

  const STYLE = `
    :host { display:block; font-family: Inter, system-ui, -apple-system, "Segoe UI", sans-serif;
            color:#1d2430; --teal:${TEAL}; }
    * { box-sizing:border-box; }
    .wrap { display:grid; grid-template-columns: 1fr 1fr; gap:16px; }
    @media (max-width:760px){ .wrap { grid-template-columns:1fr; } }
    .pane { border:1px solid #e3e8ee; border-radius:12px; background:#fff; overflow:hidden; }
    .pane h3 { margin:0; padding:10px 14px; font-size:13px; letter-spacing:.02em;
               background:#f6f8fa; border-bottom:1px solid #e3e8ee; color:#48566a; }
    .body { padding:14px; }
    .doc { white-space:pre-wrap; line-height:1.9; font-size:14px; }
    mark.ev { background:rgba(15,157,143,.16); border-bottom:2px solid var(--teal);
              border-radius:3px; padding:0 1px; cursor:pointer; }
    mark.ev.flash { background:rgba(255,193,7,.55); transition:background .2s; }
    .empty { color:#90a0b3; font-size:13px; padding:8px 0; }
    .code { border:1px solid #e3e8ee; border-radius:10px; padding:10px 12px; margin-bottom:10px; }
    .code .top { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
    .mono { font-family:"IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, monospace; }
    .ccode { font-weight:600; }
    .disp { color:#48566a; font-size:13px; }
    .badge { font-size:11px; padding:1px 7px; border-radius:999px; border:1px solid transparent; }
    .b-primary { background:var(--teal); color:#fff; }
    .b-risk { background:#fff4e5; color:#b9770e; border-color:#f3d29a; }
    .b-sys { background:#eef2f7; color:#5b6b80; }
    .b-conf { background:#eef2f7; color:#5b6b80; }
    .chips { margin-top:6px; display:flex; gap:6px; flex-wrap:wrap; }
    .chip { font-size:11px; background:#f0fdfa; color:#0c7a6f; border:1px solid #bdeae3;
            border-radius:6px; padding:1px 6px; cursor:pointer; }
    .gate { border-radius:10px; padding:10px 12px; font-size:13px; }
    .gate.pass { background:#ecfdf3; border:1px solid #bbf7d0; color:#0f7a3d; }
    .gate.block { background:#fef2f2; border:1px solid #fecaca; color:#b42318; }
    .hit { font-size:12px; margin-top:6px; }
    .sev-Critical { color:#b42318; font-weight:600; }
    .sev-Moderate { color:#b9770e; }
    .sev-Informational { color:#5b6b80; }
    .btn { font:inherit; font-size:12px; cursor:pointer; border:1px solid var(--teal);
           color:var(--teal); background:#fff; border-radius:7px; padding:3px 10px; }
    .btn:hover { background:var(--teal); color:#fff; }
    .meta { margin-top:10px; font-size:11px; color:#90a0b3; }
    .drg { margin-top:10px; font-size:12px; color:#33414f; line-height:1.6;
           background:#f1f7f6; border:1px solid #d7ece8; border-radius:8px; padding:8px 10px; }
    .drg.muted { color:#90a0b3; background:#f6f8fa; border-color:#e6e8ea; }
    .err { background:#fef2f2; border:1px solid #fecaca; color:#b42318;
           border-radius:8px; padding:8px 10px; font-size:13px; }
  `;

  function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
    ));
  }

  // Merge evidence spans from all codes/candidates and wrap them in non-overlapping <mark>s.
  function highlight(text, marks) {
    const spans = marks
      .slice()
      .sort((a, b) => a.start - b.start || b.end - a.end);
    let out = "";
    let cursor = 0;
    for (const s of spans) {
      if (s.start < cursor || s.start >= s.end || s.end > text.length) continue; // overlap/oob
      out += esc(text.slice(cursor, s.start));
      out += `<mark class="ev" data-code="${esc(s.code)}" data-start="${s.start}" data-end="${s.end}">`
        + esc(text.slice(s.start, s.end)) + `</mark>`;
      cursor = s.end;
    }
    out += esc(text.slice(cursor));
    return out;
  }

  class IcoderEmbedded extends HTMLElement {
    static get observedAttributes() { return ["base-url"]; }

    constructor() {
      super();
      this._token = null;
      this._config = { agentId: "icoder/homepage-coding-review-agent", codingSystem: "ICD-10-CN" };
      this._run = null;
      this.attachShadow({ mode: "open" });
    }

    get baseURL() { return (this.getAttribute("base-url") || "").replace(/\/$/, ""); }

    connectedCallback() {
      this.shadowRoot.innerHTML = `<style>${STYLE}</style>
        <div class="wrap">
          <section class="pane">
            <h3>去标识化病历 · 证据回链</h3>
            <div class="body"><div class="doc" id="doc"><div class="empty">尚未运行。调用 run(text) 开始编码审核。</div></div></div>
          </section>
          <section class="pane">
            <h3>编码结果 · 合规门禁</h3>
            <div class="body" id="result"><div class="empty">codes / candidates / 门禁将在这里显示。</div></div>
          </section>
        </div>`;
      this.shadowRoot.addEventListener("click", (e) => this._onClick(e));
      this._emit("ready", { baseURL: this.baseURL });
    }

    // --- lifecycle (host-driven) ---
    configureSession(opts) {
      this._token = (opts && opts.token) || null;       // host-injected; never persisted to DOM
      this._emit("auth", { authenticated: !!this._token });
      return this;
    }
    configure(cfg) {
      this._config = Object.assign({}, this._config, cfg || {});
      this._emit("configured", { ...this._config });
      return this;
    }

    async run(text) {
      if (!this._token) { this._fail("缺少令牌：host 需先 configureSession({ token })"); return; }
      if (!text || !text.trim()) { this._fail("病历文本为空"); return; }
      this._emit("run.started", {});
      try {
        const res = await fetch(`${this.baseURL}/api/coding-review/run`, {
          method: "POST",
          headers: { "Content-Type": "application/json", "Authorization": `Bearer ${this._token}` },
          body: JSON.stringify({
            text, coding_system: this._config.codingSystem, agent_id: this._config.agentId,
          }),
        });
        if (!res.ok) { this._fail(`运行失败 (HTTP ${res.status})`, await res.text()); return; }
        this._run = await res.json();
        this._render();
        this._emit("run.completed", {
          run_id: this._run.run_id,
          codes: this._run.codes.map((c) => c.code),
          candidates: this._run.candidates.map((c) => c.code),
        });
        if (this._run.compliance && this._run.compliance.human_review_required) {
          this._emit("rule-gate-triggered", {
            run_id: this._run.run_id,
            passed: this._run.compliance.passed,
            hits: this._run.compliance.hits,
          });
        }
      } catch (err) {
        this._fail("网络错误", String(err));
      }
    }

    // --- rendering ---
    _render() {
      const run = this._run;
      const allMarks = [];
      for (const c of run.codes.concat(run.candidates)) {
        for (const ev of c.evidences || []) {
          allMarks.push({ start: ev.start, end: ev.end, code: c.code });
        }
      }
      this.shadowRoot.getElementById("doc").innerHTML =
        highlight(run.redaction.text, allMarks) || `<div class="empty">无文本</div>`;

      const codeCard = (c) => {
        const badges = [
          c.is_primary ? `<span class="badge b-primary">主要诊断</span>` : "",
          c.high_risk ? `<span class="badge b-risk">高风险/易错</span>` : "",
          `<span class="badge b-sys">${esc(c.system)}</span>`,
          `<span class="badge b-conf">conf ${Number(c.confidence).toFixed(2)}</span>`,
        ].join("");
        const chips = (c.evidences || []).map((ev) =>
          `<span class="chip" data-jump="${ev.start}-${ev.end}">「${esc(ev.text)}」 [${ev.start},${ev.end})</span>`
        ).join("");
        const reviewBtn = c.status === "candidate"
          ? `<button class="btn" data-accept="${esc(c.code)}">采纳为编码</button>` : "";
        return `<div class="code">
          <div class="top"><span class="ccode mono">${esc(c.code)}</span>
            <span class="disp">${esc(c.display)}</span>${badges}
            <span style="flex:1"></span>${reviewBtn}</div>
          <div class="chips">${chips || '<span class="empty">无证据</span>'}</div>
        </div>`;
      };

      const g = run.compliance;
      const hits = (g.hits || []).map((h) =>
        `<div class="hit"><span class="sev-${h.severity}">[${h.severity}] ${esc(h.rule_id)}</span> ${esc(h.message)}</div>`
      ).join("");
      const drg = run.drg_route || {};
      const sev = drg.cc_mcc ? String(drg.cc_mcc) : "无 CC/MCC";
      const kind = drg.surgical ? "外科组" : "内科组";
      const drgRoute = drg.drg
        ? `<div class="drg">
             <div><b>DRG/DIP 分组</b> · ${kind} · 严重度 ${esc(sev)}${drg.mdc ? " · MDC " + esc(drg.mdc) : ""}</div>
             <div>ADRG <span class="mono">${esc(drg.adrg || "-")}</span> → DRG <span class="mono">${esc(drg.drg || "-")}</span> · ${esc(drg.group_name || "")}</div>
             ${drg.dip_code ? `<div>DIP <span class="mono">${esc(drg.dip_code)}</span> ${esc(drg.dip_name || "")} · 分值 ${esc(String(drg.dip_score))}</div>` : ""}
           </div>`
        : `<div class="drg muted">DRG：${esc(drg.note || "未分组")}</div>`;

      this.shadowRoot.getElementById("result").innerHTML = `
        <div style="font-size:12px;color:#48566a;margin-bottom:6px;">Codes（确信 · 可计费）</div>
        ${run.codes.map(codeCard).join("") || '<div class="empty">无</div>'}
        <div style="font-size:12px;color:#48566a;margin:12px 0 6px;">Candidates（需人工复核 · 不与 codes 合并）</div>
        ${run.candidates.map(codeCard).join("") || '<div class="empty">无</div>'}
        <div class="gate ${g.passed ? "pass" : "block"}">
          门禁：${g.passed ? "通过" : "拦截"} · 需人工复核：${g.human_review_required ? "是" : "否"}${hits}
        </div>
        ${drgRoute}
        <div class="meta">
          runtime ${esc(run.versions.runtime_version)} · ruleset ${esc(run.versions.ruleset_version)}
          · catalog ${esc(run.versions.catalog_version)} · model ${esc(run.versions.model_version)}
          · writeback_blocked=${run.production_writeback_blocked}</div>`;
    }

    _onClick(e) {
      const mark = e.target.closest("mark.ev");
      if (mark) {
        this._emit("evidence-clicked", {
          code: mark.dataset.code,
          start: Number(mark.dataset.start),
          end: Number(mark.dataset.end),
          text: mark.textContent,
        });
        return;
      }
      const chip = e.target.closest(".chip");
      if (chip && chip.dataset.jump) { this._flash(chip.dataset.jump); return; }

      const accept = e.target.closest("[data-accept]");
      if (accept) { this._submitReview(accept.getAttribute("data-accept")); return; }
    }

    _flash(jump) {
      const [s, en] = jump.split("-");
      const m = this.shadowRoot.querySelector(`mark.ev[data-start="${s}"][data-end="${en}"]`);
      if (!m) return;
      m.scrollIntoView({ block: "center", behavior: "smooth" });
      m.classList.add("flash");
      setTimeout(() => m.classList.remove("flash"), 900);
    }

    async _submitReview(code) {
      this._emit("code-overridden", { code, decision: "accept" });
      try {
        const res = await fetch(`${this.baseURL}/api/coding-review/${this._run.run_id}/human-review`, {
          method: "POST",
          headers: { "Content-Type": "application/json", "Authorization": `Bearer ${this._token}` },
          body: JSON.stringify({ decision: "accept", code }),
        });
        if (!res.ok) { this._fail(`人工复核失败 (HTTP ${res.status})`, await res.text()); return; }
        const data = await res.json();
        this._emit("human-review-submitted", data);
      } catch (err) {
        this._fail("人工复核网络错误", String(err));
      }
    }

    _fail(message, detail) {
      const r = this.shadowRoot.getElementById("result");
      if (r) r.innerHTML = `<div class="err">${esc(message)}</div>`;
      this._emit("error.triggered", { message, detail: detail || "" });
    }

    _emit(type, payload) {
      this.dispatchEvent(new CustomEvent("embedded-event", {
        detail: { type, payload }, bubbles: true, composed: true,
      }));
    }
  }

  if (!customElements.get("icoder-embedded")) {
    customElements.define("icoder-embedded", IcoderEmbedded);
  }
})();
