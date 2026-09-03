"""Phase 4-C: ``get_guidelines`` handler tests.

Verifies the new tool that returns chapter-level + general ICD-10-CN
coding conventions (mirrors Corti Code Validation's ``guidelines`` tool).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


pytestmark = pytest.mark.asyncio


async def test_get_guidelines_returns_general_rules_without_code():
    """Without a code param, returns general rules + empty chapter info."""
    from app.icoder.mcp.handlers.get_guidelines import handle

    out = await handle({}, MagicMock())

    assert out["chapter"] == ""
    assert out["chapter_conventions"] == []
    # 10 general rules
    assert len(out["general_rules"]) >= 10
    assert out["source"] == "internal_kb"
    # Spot-check a few rules
    assert any("主诊断" in r for r in out["general_rules"])
    assert any("最具体" in r for r in out["general_rules"])


async def test_get_guidelines_returns_chapter_conventions_for_known_code():
    """When a code is given, returns chapter-specific conventions."""
    from app.icoder.mcp.handlers.get_guidelines import handle

    entry = MagicMock()
    entry.chapter_no = "9"
    entry.chapter_name = "循环系统疾病"

    loader = MagicMock()
    loader.get = MagicMock(return_value=entry)
    loader.chapter_for = MagicMock(return_value="第9章 循环系统疾病")

    with patch("app.services.icd10cn_loader.get_loader", return_value=loader):
        out = await handle({"code": "I50.900"}, MagicMock())

    assert out["chapter"] == "第9章 循环系统疾病"
    # Chapter 9 has conventions (per the inline KB)
    assert len(out["chapter_conventions"]) >= 2
    # Chapter 9 should mention heart/circulatory
    assert any("循环系统" in c or "心肌梗死" in c or "心力衰竭" in c
               for c in out["chapter_conventions"])
    # General rules still present
    assert len(out["general_rules"]) >= 10
    assert out["source"] == "internal_kb"


async def test_get_guidelines_unknown_chapter_returns_only_general_rules():
    """Code with an unknown chapter_no returns only general rules (no chapter convs)."""
    from app.icoder.mcp.handlers.get_guidelines import handle

    entry = MagicMock()
    entry.chapter_no = "99"  # not in CHAPTER_CONVENTIONS
    entry.chapter_name = "Unknown"

    loader = MagicMock()
    loader.get = MagicMock(return_value=entry)
    loader.chapter_for = MagicMock(return_value="第99章 Unknown")

    with patch("app.services.icd10cn_loader.get_loader", return_value=loader):
        out = await handle({"code": "X99.9"}, MagicMock())

    assert out["chapter"] == "第99章 Unknown"
    assert out["chapter_conventions"] == []  # no conventions for chapter 99
    assert len(out["general_rules"]) >= 10


async def test_get_guidelines_code_not_in_catalog():
    """When code is not in catalog, returns only general rules."""
    from app.icoder.mcp.handlers.get_guidelines import handle

    loader = MagicMock()
    loader.get = MagicMock(return_value=None)
    loader.chapter_for = MagicMock(return_value="")

    with patch("app.services.icd10cn_loader.get_loader", return_value=loader):
        out = await handle({"code": "X99.999"}, MagicMock())

    assert out["chapter"] == ""
    assert out["chapter_conventions"] == []
    assert len(out["general_rules"]) >= 10


async def test_get_guidelines_loader_unavailable_returns_general_rules():
    """When loader raises, returns only general rules (graceful degradation)."""
    from app.icoder.mcp.handlers.get_guidelines import handle

    with patch(
        "app.services.icd10cn_loader.get_loader",
        side_effect=RuntimeError("asset dir not mounted"),
    ):
        out = await handle({"code": "I50.900"}, MagicMock())

    assert out["chapter"] == ""
    assert out["chapter_conventions"] == []
    assert len(out["general_rules"]) >= 10
    assert out["source"] == "internal_kb"


async def test_get_guidelines_empty_code_returns_general_rules():
    """Empty code string returns only general rules."""
    from app.icoder.mcp.handlers.get_guidelines import handle

    out = await handle({"code": ""}, MagicMock())

    assert out["chapter"] == ""
    assert out["chapter_conventions"] == []
    assert len(out["general_rules"]) >= 10
