"""M3 E2E Product Validation — 链路 9 嵌入组件 Demo 3 组件渲染.

自动化验证 (前端组件 import 路径存在):
- IcoderReviewPanel.tsx
- IcoderEvidenceViewer.tsx
- IcoderTraceViewer.tsx
- EmbedDemoCodingReviewPage.tsx
"""

from __future__ import annotations

import re
import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_ROOT = REPO_ROOT.parent / "frontend"


def test_icoder_review_panel_exists():
    """链路 9.1: IcoderReviewPanel.tsx 存在."""
    path = FRONTEND_ROOT / "src" / "components" / "embed" / "IcoderReviewPanel.tsx"
    assert path.exists(), f"missing {path}"


def test_icoder_evidence_viewer_exists():
    """链路 9.2: IcoderEvidenceViewer.tsx 存在."""
    path = FRONTEND_ROOT / "src" / "components" / "embed" / "IcoderEvidenceViewer.tsx"
    assert path.exists(), f"missing {path}"


def test_icoder_trace_viewer_exists():
    """链路 9.3: IcoderTraceViewer.tsx 存在."""
    path = FRONTEND_ROOT / "src" / "components" / "embed" / "IcoderTraceViewer.tsx"
    assert path.exists(), f"missing {path}"


def test_embed_demo_page_exists():
    """链路 9.4: EmbedDemoCodingReviewPage.tsx 存在."""
    path = FRONTEND_ROOT / "src" / "pages" / "EmbedDemoCodingReviewPage.tsx"
    assert path.exists(), f"missing {path}"


def test_embed_demo_page_uses_three_components():
    """链路 9.5: EmbedDemoCodingReviewPage.tsx 同时 import 3 个组件."""
    page = FRONTEND_ROOT / "src" / "pages" / "EmbedDemoCodingReviewPage.tsx"
    content = page.read_text(encoding="utf-8")
    assert "IcoderReviewPanel" in content
    assert "IcoderEvidenceViewer" in content
    assert "IcoderTraceViewer" in content


def test_embed_components_are_chromeless():
    """链路 9.6: 3 个 Embed 组件是 chrome-less (不依赖 iCoDer Layout)."""
    for fname in ("IcoderReviewPanel.tsx", "IcoderEvidenceViewer.tsx", "IcoderTraceViewer.tsx"):
        path = FRONTEND_ROOT / "src" / "components" / "embed" / fname
        content = path.read_text(encoding="utf-8")
        # 不应 import Layout 或 useAuthStore (会引入 app shell)
        assert "../layout/Layout" not in content, \
            f"{fname} should not depend on iCoDer Layout"


def test_embed_demo_route_registered():
    """链路 9.7: /embed-demo/coding-review 路由已注册."""
    app_tsx = FRONTEND_ROOT / "src" / "App.tsx"
    content = app_tsx.read_text(encoding="utf-8")
    assert "embed-demo/coding-review" in content
    assert "EmbedDemoCodingReviewPage" in content


def test_embed_demo_disclaimer_present():
    """链路 9.8: EmbedDemoCodingReviewPage 含 disclaimer."""
    page = FRONTEND_ROOT / "src" / "pages" / "EmbedDemoCodingReviewPage.tsx"
    content = page.read_text(encoding="utf-8")
    # disclaimer 关键词
    assert "embed" in content.lower()
    assert "第三方" in content or "HIS" in content
    # 不能写成 "iCoDer 全部产品定位"
    # (反向: 出现 "不代表 iCoDer 全部产品定位" 或 "仅展示 embed 组件能力")
    assert "不代表 iCoDer 全部产品定位" in content or "仅展示 embed 组件能力" in content