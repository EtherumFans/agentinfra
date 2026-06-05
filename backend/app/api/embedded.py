"""Embedded Assistant API — serves the <icoder-assistant> Web Component JS bundle."""

from fastapi import APIRouter
from fastapi.responses import Response, HTMLResponse
from pathlib import Path

router = APIRouter(prefix="/api/embedded", tags=["embedded"])


@router.get("/assistant.js")
async def embedded_assistant_js():
    """Serve the iCoDer Assistant Web Component JS bundle."""
    js_path = Path(__file__).parent.parent.parent.parent / "packages" / "icoder-embedded" / "src" / "icoder-assistant.ts"
    if js_path.exists():
        content = js_path.read_text(encoding="utf-8")
        return Response(content=content, media_type="application/javascript")
    return Response(content="// iCoDer Assistant — build the @icoder/embedded package first", media_type="application/javascript")


@router.get("/preview")
async def embedded_assistant_preview():
    """Preview page for the iCoDer Assistant Web Component."""
    return HTMLResponse(content="""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>iCoDer Assistant Preview</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", sans-serif; background: #f5f5f7; display: flex; height: 100vh; }
.sidebar { width: 280px; background: #fff; border-right: 1px solid #e5e5ea; padding: 20px; display: flex; flex-direction: column; gap: 16px; }
.sidebar h2 { font-size: 18px; font-weight: 600; color: #1d1d1f; }
.sidebar label { font-size: 12px; font-weight: 500; color: #86868b; display: block; margin-bottom: 4px; }
.sidebar input, .sidebar select { width: 100%; padding: 8px 12px; border: 1px solid #e5e5ea; border-radius: 8px; font-size: 13px; outline: none; }
.sidebar input:focus { border-color: #007aff; }
.main { flex: 1; display: flex; align-items: center; justify-content: center; padding: 24px; }
.assistant-wrapper { width: 400px; height: 600px; }
</style>
</head>
<body>
<div class="sidebar">
  <h2>iCoDer Assistant</h2>
  <div>
    <label>Runtime URL</label>
    <input id="baseUrl" value="http://localhost:8000" placeholder="http://icoder-server:8000">
  </div>
  <div>
    <label>Access Token</label>
    <input id="token" type="password" placeholder="JWT access token">
  </div>
  <div>
    <label>Agent</label>
    <select id="agentRef">
      <option value="medical-coding-agent-1.0.0">Medical Coding Agent</option>
      <option value="compliance-guardrail-1.0.0">合规护栏</option>
      <option value="code-reconciler-1.0.0">Code Reconciler</option>
    </select>
  </div>
  <div>
    <label>Patient Context (JSON)</label>
    <input id="patientCtx" placeholder='{"name":"张三","patientId":"P001"}'>
  </div>
  <div>
    <label>Theme</label>
    <select id="theme"><option value="light">Light</option><option value="dark">Dark</option></select>
  </div>
  <p style="font-size:11px;color:#86868b;margin-top:auto;">
    复制 &lt;icoder-assistant&gt; 标签到你的 HIS/EMR 页面即可嵌入。
  </p>
</div>
<div class="main">
  <div class="assistant-wrapper">
    <icoder-assistant id="assistant" base-url="http://localhost:8000" agent-ref="medical-coding-agent-1.0.0" theme="light"></icoder-assistant>
  </div>
</div>
<script type="module">
import { iCoDerAssistant } from '/api/embedded/assistant.js';
const el = document.getElementById('assistant');

document.getElementById('baseUrl').addEventListener('input', e => el.setAttribute('base-url', e.target.value));
document.getElementById('token').addEventListener('input', e => el.setAttribute('access-token', e.target.value));
document.getElementById('agentRef').addEventListener('change', e => el.setAttribute('agent-ref', e.target.value));
document.getElementById('theme').addEventListener('change', e => el.setAttribute('theme', e.target.value));

document.getElementById('patientCtx').addEventListener('change', e => {
  try { el.setPatientContext(JSON.parse(e.target.value)); } catch {}
});

el.addEventListener('ready', () => console.log('iCoDer Assistant ready'));
el.addEventListener('coding.completed', e => console.log('Coding completed', e.detail));
el.addEventListener('error', e => console.error('Assistant error', e.detail));
</script>
</body>
</html>""")
