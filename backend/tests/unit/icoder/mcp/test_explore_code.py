"""Phase 4-C: ``explore_code`` handler tests.

Verifies parent / siblings / children traversal (mirrors Corti Code
Validation's ``explore`` tool).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


pytestmark = pytest.mark.asyncio


def _make_entry(
    *, code: str, name_cn: str = "",
    chapter_no: str = "9", chapter_name: str = "循环系统疾病",
    category_code: str = "",
) -> MagicMock:
    e = MagicMock()
    e.code = code
    e.name_cn = name_cn
    e.chapter_no = chapter_no
    e.chapter_name = chapter_name
    e.category_code = category_code
    return e


# ── leaf code: parent + siblings + children ──────────────────────────


async def test_explore_code_leaf_code_returns_parent_and_siblings():
    """A leaf code (in catalog) returns parent + siblings (same category)."""
    from app.icoder.mcp.handlers.explore_code import handle

    # I25.10, I25.110, I25.5 share category_code="I25"
    target = _make_entry(code="I25.10", name_cn="动脉粥样硬化性心脏病",
                          category_code="I25", chapter_no="9",
                          chapter_name="循环系统疾病")
    sibling1 = _make_entry(code="I25.110", name_cn="粥样硬化性心脏病",
                            category_code="I25", chapter_no="9")
    sibling2 = _make_entry(code="I25.5", name_cn="慢性缺血性心脏病",
                            category_code="I25", chapter_no="9")

    loader = MagicMock()
    loader.has = MagicMock(return_value=True)
    loader.get = MagicMock(return_value=target)
    loader.chapter_for = MagicMock(return_value="第9章 循环系统疾病")
    loader.all_codes = MagicMock(return_value=[target, sibling1, sibling2])

    with patch("app.services.icd10cn_loader.get_loader", return_value=loader):
        out = await handle({"code": "I25.10"}, MagicMock())

    assert out["code"] == "I25.10"
    assert out["in_catalog"] is True
    # parent has chapter info
    assert out["parent"] is not None
    assert out["parent"]["chapter"] == "第9章 循环系统疾病"
    assert out["parent"]["chapter_no"] == "9"
    assert out["parent"]["category_code"] == "I25"
    # siblings — same category, excluding self
    assert len(out["siblings"]) == 2
    sibling_codes = [s["code"] for s in out["siblings"]]
    assert "I25.110" in sibling_codes
    assert "I25.5" in sibling_codes
    assert "I25.10" not in sibling_codes  # self excluded
    # children — I25.10 has no further subdivisions in this mock
    assert out["children"] == []


# ── category code (prefix): children present ─────────────────────────


async def test_explore_code_category_prefix_returns_children():
    """A category prefix (e.g. 'I25') returns children subdivisions."""
    from app.icoder.mcp.handlers.explore_code import handle

    # I25 itself not in catalog, but I25.10 / I25.110 / I25.5 are
    child1 = _make_entry(code="I25.10", name_cn="动脉粥样硬化性心脏病",
                          category_code="I25", chapter_no="9")
    child2 = _make_entry(code="I25.110", name_cn="粥样硬化性心脏病",
                          category_code="I25", chapter_no="9")
    child3 = _make_entry(code="I25.5", name_cn="慢性缺血性心脏病",
                          category_code="I25", chapter_no="9")

    loader = MagicMock()
    loader.has = MagicMock(return_value=False)  # I25 itself not in catalog
    # get(I25) returns None, but get(child_code) returns the entry
    loader.get = MagicMock(side_effect=lambda c: {
        "I25.10": child1, "I25.110": child2, "I25.5": child3,
    }.get(c))
    loader.chapter_for = MagicMock(return_value="第9章 循环系统疾病")
    loader.all_codes = MagicMock(return_value=[child1, child2, child3])

    with patch("app.services.icd10cn_loader.get_loader", return_value=loader):
        out = await handle({"code": "I25"}, MagicMock())

    assert out["code"] == "I25"
    assert out["in_catalog"] is False  # I25 itself not in catalog
    # children — subdivisions starting with "I25."
    assert len(out["children"]) == 3
    child_codes = [c["code"] for c in out["children"]]
    assert child_codes == ["I25.10", "I25.110", "I25.5"]  # sorted
    # parent — uses first child's metadata
    assert out["parent"] is not None
    assert out["parent"]["category_code"] == "I25"


# ── unknown code ─────────────────────────────────────────────────────


async def test_explore_code_unknown_code_returns_empty():
    """Unknown code with no children → parent=None, siblings=[], children=[]."""
    from app.icoder.mcp.handlers.explore_code import handle

    loader = MagicMock()
    loader.has = MagicMock(return_value=False)
    loader.get = MagicMock(return_value=None)
    loader.all_codes = MagicMock(return_value=[])  # no children

    with patch("app.services.icd10cn_loader.get_loader", return_value=loader):
        out = await handle({"code": "X99.999"}, MagicMock())

    assert out["in_catalog"] is False
    assert out["parent"] is None
    assert out["siblings"] == []
    assert out["children"] == []


# ── empty code ───────────────────────────────────────────────────────


async def test_explore_code_empty_code_returns_empty():
    """Empty code string returns empty envelope, no crash."""
    from app.icoder.mcp.handlers.explore_code import handle

    out = await handle({"code": ""}, MagicMock())

    assert out["code"] == ""
    assert out["in_catalog"] is False
    assert out["parent"] is None
    assert out["siblings"] == []
    assert out["children"] == []


# ── siblings cap at 20 ───────────────────────────────────────────────


async def test_explore_code_siblings_capped_at_20():
    """When the category has 25 codes, siblings list is capped at 20."""
    from app.icoder.mcp.handlers.explore_code import handle

    target = _make_entry(code="I25.10", category_code="I25", chapter_no="9")
    others = [
        _make_entry(code=f"I25.{i:02d}", category_code="I25", chapter_no="9")
        for i in range(25) if f"I25.{i:02d}" != "I25.10"
    ]

    loader = MagicMock()
    loader.has = MagicMock(return_value=True)
    loader.get = MagicMock(return_value=target)
    loader.chapter_for = MagicMock(return_value="第9章")
    loader.all_codes = MagicMock(return_value=[target] + others)

    with patch("app.services.icd10cn_loader.get_loader", return_value=loader):
        out = await handle({"code": "I25.10"}, MagicMock())

    assert len(out["siblings"]) <= 20


# ── loader unavailable ───────────────────────────────────────────────


async def test_explore_code_loader_unavailable_returns_empty():
    """When loader raises, returns empty envelope (graceful)."""
    from app.icoder.mcp.handlers.explore_code import handle

    with patch(
        "app.services.icd10cn_loader.get_loader",
        side_effect=RuntimeError("asset dir not mounted"),
    ):
        out = await handle({"code": "I25.10"}, MagicMock())

    assert out["in_catalog"] is False
    assert out["parent"] is None
    assert out["siblings"] == []
    assert out["children"] == []


# ── children sort by code ────────────────────────────────────────────


async def test_explore_code_children_sorted_by_code():
    """Children list is sorted alphabetically."""
    from app.icoder.mcp.handlers.explore_code import handle

    c1 = _make_entry(code="I25.5", category_code="I25", chapter_no="9")
    c2 = _make_entry(code="I25.10", category_code="I25", chapter_no="9")
    c3 = _make_entry(code="I25.110", category_code="I25", chapter_no="9")

    loader = MagicMock()
    loader.has = MagicMock(return_value=False)
    loader.get = MagicMock(side_effect=lambda c: {
        "I25.10": c2, "I25.110": c3, "I25.5": c1,
    }.get(c))
    loader.chapter_for = MagicMock(return_value="第9章")
    loader.all_codes = MagicMock(return_value=[c1, c2, c3])  # unsorted

    with patch("app.services.icd10cn_loader.get_loader", return_value=loader):
        out = await handle({"code": "I25"}, MagicMock())

    child_codes = [c["code"] for c in out["children"]]
    assert child_codes == ["I25.10", "I25.110", "I25.5"]
