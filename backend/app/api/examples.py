"""Phase 7 Gate 1 — Partner Demo Static Mount.

Serves the three partner-facing demos through stable backend paths:

    GET /examples/                      — index
    GET /examples/medical-coding/       — Medical Coding demo
    GET /examples/cdi/                  — CDI demo
    GET /examples/drg-dip/              — DRG/DIP demo
    GET /examples/config.js             — partner config (env-driven, no secrets)

Phase 7 §6 requirements honored:
- 使用正式构建产物 (demos are production HTML, not src dev files)
- 可配置 Base URL (via config.js + .env)
- 具备版本号 (X-iCoDer-Demo-Version header + meta tag in HTML)
- 支持 Cache-Control (no-cache for HTML, immutable for the assistant.js bundle)
- 支持 CSP (restrictive: self + the widget script + inline styles/scripts the demos emit)
- 正确 MIME 类型 (text/html for demos, application/javascript for config.js)
- 不暴露源码目录 (only the 3 whitelisted demo filenames resolve; everything else 404)
- 不允许目录遍历 (no path parameters; fixed whitelist)

Demos are independent of Console per §6.2:
- No React router dependency (demos are plain HTML + module scripts)
- No Console Store dependency
- No Console cookie dependency (demos read window.icoderConfig)
- No monorepo source import (demos load /api/embedded/assistant.js, the compiled dist)
- No undocumented API dependency

The demos continue to work in "Console JWT mode" for local dev (developer pastes
their JWT into the form). Gate 5 will add client_credentials mode so partners
without a Console session can authenticate.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Final

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, Response

router = APIRouter(prefix="/examples", tags=["examples"])

_PKG_ROOT: Final[Path] = (
    Path(__file__).parent.parent.parent.parent / "packages" / "icoder-embedded"
)
_DEMOS_DIR: Final[Path] = _PKG_ROOT / "demos"

_DEMO_VERSION = "1.0.0-phase7-gate6"
_DEMO_INDEX: Final[dict[str, Path]] = {
    "medical-coding": _DEMOS_DIR / "medical-coding-demo.html",
    "cdi": _DEMOS_DIR / "cdi-demo.html",
    "drg-dip": _DEMOS_DIR / "drg-dip-demo.html",
}

_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    # connect-src allows both 127.0.0.1 and localhost forms of the dev
    # origin so partners running the demo locally don't trip CSP when
    # their browser resolves the serving host differently from the
    # widget's configured baseURL. Production deployments serve the
    # demo and the API from the same canonical hostname, so 'self'
    # covers them.
    "connect-src 'self' http://localhost:8000 http://127.0.0.1:8000 "
    "http://localhost:3000 http://127.0.0.1:3000; "
    "font-src 'self' data:; "
    "frame-src 'none'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)
_HTML_CACHE = "no-cache, must-revalidate"
_JS_CACHE = "no-cache, must-revalidate"


def _common_headers() -> dict[str, str]:
    return {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "X-iCoDer-Demo-Version": _DEMO_VERSION,
    }


def _read_demo(name: str) -> str:
    path = _DEMO_INDEX[name]
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"demo asset missing: {name}")
    return path.read_text(encoding="utf-8")


@router.get("/", response_class=HTMLResponse)
async def examples_index():
    """Phase 7 Gate 1 demo index — lists all 3 partner demos."""
    body = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>iCoDer Partner Demos</title>
<meta name="version" content="{_DEMO_VERSION}">
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", sans-serif; background: #f5f5f7; color: #1d1d1f; padding: 40px 24px; }}
.container {{ max-width: 720px; margin: 0 auto; }}
h1 {{ font-size: 28px; margin-bottom: 4px; }}
.subtitle {{ font-size: 13px; color: #86868b; margin-bottom: 24px; }}
.card {{ background: #fff; border-radius: 12px; padding: 20px; margin-bottom: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }}
.card h3 {{ font-size: 16px; margin-bottom: 6px; }}
.card p {{ font-size: 13px; color: #515154; line-height: 1.5; margin-bottom: 12px; }}
.card a {{ color: #007aff; text-decoration: none; font-size: 13px; font-weight: 500; }}
.card a:hover {{ text-decoration: underline; }}
.meta {{ font-size: 11px; color: #86868b; margin-top: 12px; }}
code {{ background: #f2f2f7; padding: 2px 6px; border-radius: 4px; font-size: 11px; }}
</style>
</head>
<body>
<div class="container">
  <h1>iCoDer Partner Demos</h1>
  <p class="subtitle">Phase 7 Gate 1 · 独立 · 静态挂载 · version {_DEMO_VERSION}</p>

  <div class="card">
    <h3>Medical Coding (医疗编码)</h3>
    <p>HIS/EMR 嵌入 medical-coding-agent · 场景: 左肺结节 + 肋骨骨折 ICD-10-CN 编码</p>
    <a href="/examples/medical-coding/">→ 打开 Medical Coding demo</a>
  </div>

  <div class="card">
    <h3>CDI (临床文档改进)</h3>
    <p>HIS/EMR 嵌入 cdi agent · 场景: 心衰入院 关键内涵缺口识别 + 中立澄清任务</p>
    <a href="/examples/cdi/">→ 打开 CDI demo</a>
  </div>

  <div class="card">
    <h3>DRG/DIP (分组合规风险)</h3>
    <p>HIS/EMR 嵌入 drg-analyzer agent · 场景: 急性脑梗死合并房颤/高血压/糖尿病 DRG 分组风险</p>
    <a href="/examples/drg-dip/">→ 打开 DRG/DIP demo</a>
  </div>

  <p class="meta">
    独立于 Console (无 React 路由 / Store / Cookie 依赖).<br>
    配置: <code>GET /examples/config.js</code> · 后端读取 <code>ICODER_BASE_URL</code> 等环境变量.<br>
    构建: 服务正式 HTML 产物 (非 src 临时加载) · CSP + nosniff + frame-ancestors none.
  </p>
</div>
</body>
</html>"""
    return HTMLResponse(
        content=body,
        headers={
            **_common_headers(),
            "Content-Security-Policy": _CSP,
            "Cache-Control": _HTML_CACHE,
        },
    )


@router.get("/medical-coding/", response_class=HTMLResponse)
async def example_medical_coding():
    return _serve_demo("medical-coding")


@router.get("/cdi/", response_class=HTMLResponse)
async def example_cdi():
    return _serve_demo("cdi")


@router.get("/drg-dip/", response_class=HTMLResponse)
async def example_drg_dip():
    return _serve_demo("drg-dip")


def _serve_demo(name: str) -> HTMLResponse:
    """Strict whitelist dispatch — no path parameter interpolation."""
    if name not in _DEMO_INDEX:
        raise HTTPException(status_code=404, detail="unknown demo")
    body = _read_demo(name)
    return HTMLResponse(
        content=body,
        headers={
            **_common_headers(),
            "Content-Security-Policy": _CSP,
            "Cache-Control": _HTML_CACHE,
        },
    )


@router.get("/config.js")
async def example_config_js():
    """Partner-app config — env-driven, no secrets.

    Partners copy `.env.example` → `.env`, set their client_id / agent_ref,
    and the backend injects those values into this JS module. The demo HTML
    loads `/examples/config.js` before init and reads `window.icoderConfig`.

    Per Phase 7 §6.3, secrets (ICODER_API_CLIENT_SECRET) are NEVER shipped
    to the browser. Partners obtain tokens via their own backend using
    client_credentials against /api/oauth/realms/{realm}/token (Gate 5).
    """
    # Default to empty so the demo auto-detects window.location.origin
    # in the browser (Gate 10 fix). Operator overrides via ICODER_BASE_URL
    # when the API lives on a different host than the page-serving origin.
    base_url = os.environ.get("ICODER_BASE_URL", "").rstrip("/")
    agent_ref = os.environ.get("ICODER_AGENT_REF", "medical-coding-agent")
    api_client_id = os.environ.get("ICODER_API_CLIENT_ID", "")
    organization_id = os.environ.get("ICODER_ORGANIZATION_ID", "")
    body = f"""// Phase 7 Gate 1 partner demo config — auto-generated from server env.
// DO NOT commit real secrets here. Server reads from .env (see .env.example).
window.icoderConfig = {{
  baseUrl: {repr(base_url)},
  agentRef: {repr(agent_ref)},
  apiClientId: {repr(api_client_id)},
  organizationId: {repr(organization_id)},
  demoVersion: {repr(_DEMO_VERSION)},
}};
"""
    return Response(
        content=body,
        media_type="application/javascript; charset=utf-8",
        headers={
            **_common_headers(),
            "Content-Security-Policy": _CSP,
            "Cache-Control": _JS_CACHE,
        },
    )


@router.get("/{path:path}")
async def example_catchall(path: str):
    """Strict deny-by-default — only the 3 whitelisted demos + config.js resolve.

    This catches directory traversal attempts (e.g. /examples/../../etc/passwd)
    and any path not in the whitelist. Per Phase 7 §6.1: 不允许目录遍历.
    """
    raise HTTPException(status_code=404, detail="not found")
