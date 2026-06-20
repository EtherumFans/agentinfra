"""M3 E2E Product Validation — 链路 4 + 链路 1 Workbench 三栏布局 + Studio 可见性."""

from __future__ import annotations

import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_ROOT = REPO_ROOT.parent / "frontend"


def test_workbench_page_exists():
    """链路 4.1: CodingReviewWorkbenchPage.tsx 存在."""
    path = FRONTEND_ROOT / "src" / "pages" / "CodingReviewWorkbenchPage.tsx"
    assert path.exists(), f"missing {path}"


def test_workbench_three_column_layout():
    """链路 4.2: Workbench 使用 3 列 grid (col-span-3 / col-span-5 / col-span-4)."""
    page = FRONTEND_ROOT / "src" / "pages" / "CodingReviewWorkbenchPage.tsx"
    content = page.read_text(encoding="utf-8")
    assert "col-span-3" in content, "left column (col-span-3) must exist"
    assert "col-span-5" in content, "middle column (col-span-5) must exist"
    assert "col-span-4" in content, "right column (col-span-4) must exist"


def test_workbench_left_column_has_input():
    """链路 4.3: 左列含输入参数 + 病历原文 + Run 按钮."""
    page = FRONTEND_ROOT / "src" / "pages" / "CodingReviewWorkbenchPage.tsx"
    content = page.read_text(encoding="utf-8")
    assert "primary_disease_codes" in content or "primaryCodes" in content
    assert "encounter_text" in content or "encounterText" in content
    assert "运行 14 阶段审核" in content or "handleRun" in content


def test_workbench_middle_column_has_diagnosis_cards():
    """链路 4.4: 中列含主诊断 / 其他诊断 / 手术卡片."""
    page = FRONTEND_ROOT / "src" / "pages" / "CodingReviewWorkbenchPage.tsx"
    content = page.read_text(encoding="utf-8")
    assert "primary_diagnosis" in content or "primaryDiagnosis" in content
    assert "secondary_diagnoses" in content or "secondaryDiagnoses" in content
    assert "procedures" in content


def test_workbench_right_column_has_high_risk():
    """链路 4.5: 右列含高风险易错编码点面板."""
    page = FRONTEND_ROOT / "src" / "pages" / "CodingReviewWorkbenchPage.tsx"
    content = page.read_text(encoding="utf-8")
    assert "HighRiskCodingPointPanel" in content


def test_workbench_right_column_has_evidence_viewer():
    """链路 4.6: 右列含证据回链."""
    page = FRONTEND_ROOT / "src" / "pages" / "CodingReviewWorkbenchPage.tsx"
    content = page.read_text(encoding="utf-8")
    assert "EvidenceViewer" in content


def test_workbench_bottom_has_run_trace():
    """链路 4.7: 底部 RunTraceTimeline."""
    page = FRONTEND_ROOT / "src" / "pages" / "CodingReviewWorkbenchPage.tsx"
    content = page.read_text(encoding="utf-8")
    assert "RunTraceTimeline" in content


def test_workbench_human_review_actions():
    """链路 4.8: 人工复核操作按钮存在."""
    page = FRONTEND_ROOT / "src" / "pages" / "CodingReviewWorkbenchPage.tsx"
    content = page.read_text(encoding="utf-8")
    assert "handleHumanReview" in content
    assert "reviewer" in content or "reviewerName" in content


def test_workbench_route_registered():
    """链路 1 + 4.9: 路由已注册."""
    app_tsx = FRONTEND_ROOT / "src" / "App.tsx"
    content = app_tsx.read_text(encoding="utf-8")
    # 路由可以是 "studio/agents/homepage-coding-review" (相对父 /) 或
    # "/studio/agents/homepage-coding-review" (绝对) — React Router 两种都合法
    assert "studio/agents/homepage-coding-review" in content
    assert "runtime/coding-review" in content


def test_workbench_disclaimer_visible():
    """链路 1 红线: Workbench 顶部 disclaimer 显式声明样板 Agent + Pipeline Validation."""
    page = FRONTEND_ROOT / "src" / "pages" / "CodingReviewWorkbenchPage.tsx"
    content = page.read_text(encoding="utf-8")
    # 必含 "iCoDer 第一个官方样板 Agent" 或类似
    assert "样板 Agent" in content or "reference agent" in content.lower()
    # 必含 "pipeline validation" 或 "不代表模型效果"
    assert "pipeline validation" in content.lower() or "不代表模型效果" in content