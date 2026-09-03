"""Phase 4-C: ``verify_code`` extended output tests.

Verifies the new fields added to ``verify_code`` to mirror Corti Code
Validation's ``verify`` tool:
  - ``assignable`` — leaf vs category distinction
  - ``parent_hierarchy`` — [chapter_no, category_code, code]
  - ``children_if_non_assignable`` — subdivisions when assignable=False
  - ``excludes1`` / ``excludes2`` / ``code_first_notes`` /
    ``use_additional_code_notes`` — forward-compat slots (Phase 4-C: empty)

Uses ``unittest.mock.patch`` on ``app.services.icd10cn_loader.get_loader``
so no real catalog file is needed.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


pytestmark = pytest.mark.asyncio


def _make_entry(
    *, code: str = "I50.900", name_cn: str = "心力衰竭",
    chapter_no: str = "9", chapter_name: str = "循环系统疾病",
    category_code: str = "I50",
    synonyms_cn: tuple[str, ...] = ("心衰", "充血性心力衰竭"),
) -> MagicMock:
    e = MagicMock()
    e.code = code
    e.name_cn = name_cn
    e.chapter_no = chapter_no
    e.chapter_name = chapter_name
    e.category_code = category_code
    e.synonyms_cn = synonyms_cn
    return e


# ── assignable leaf code ─────────────────────────────────────────────


async def test_verify_code_assignable_leaf_code():
    """A code in the catalog with no children → assignable=True, no children list."""
    from app.icoder.mcp.handlers.verify_code import handle

    entry = _make_entry(code="I50.900", category_code="I50")
    loader = MagicMock()
    loader.has = MagicMock(return_value=True)
    loader.get = MagicMock(return_value=entry)
    loader.chapter_for = MagicMock(return_value="第9章 循环系统疾病")
    loader.all_codes = MagicMock(return_value=[entry])  # only this code

    with patch("app.services.icd10cn_loader.get_loader", return_value=loader):
        out = await handle({"code": "I50.900"}, MagicMock())

    assert out["in_catalog"] is True
    assert out["assignable"] is True
    assert out["code"] == "I50.900"
    assert out["name"] == "心力衰竭"
    assert out["chapter"] == "第9章 循环系统疾病"
    # parent_hierarchy: [chapter_no, category_code, code]
    assert out["parent_hierarchy"] == ["9", "I50", "I50.900"]
    # assignable=True → no children list
    assert out["children_if_non_assignable"] == []
    # Forward-compat slots — empty in Phase 4-C
    assert out["excludes1"] == []
    assert out["excludes2"] == []
    assert out["code_first_notes"] == []
    assert out["use_additional_code_notes"] == []
    # aliases preserved (top 10 Chinese synonyms)
    assert "心衰" in out["aliases"]
    assert "充血性心力衰竭" in out["aliases"]


# ── non-assignable category code ─────────────────────────────────────


async def test_verify_code_non_assignable_category_code():
    """A category prefix (e.g. 'I25') with subdivisions → assignable=False."""
    from app.icoder.mcp.handlers.verify_code import handle

    # The category "I25" is NOT in the catalog directly.
    # Children: I25.10, I25.110, I25.5 — these ARE in the catalog.
    child1 = _make_entry(code="I25.10", name_cn="动脉粥样硬化性心脏病",
                         category_code="I25", chapter_no="9")
    child2 = _make_entry(code="I25.110", name_cn="粥样硬化性心脏病",
                         category_code="I25", chapter_no="9")
    child3 = _make_entry(code="I25.5", name_cn="慢性缺血性心脏病",
                         category_code="I25", chapter_no="9")

    loader = MagicMock()
    loader.has = MagicMock(return_value=False)  # 'I25' itself not in catalog
    # When checking children, get() is called on child codes.
    loader.get = MagicMock(return_value=child1)
    loader.chapter_for = MagicMock(return_value="第9章 循环系统疾病")
    loader.all_codes = MagicMock(return_value=[child1, child2, child3])

    with patch("app.services.icd10cn_loader.get_loader", return_value=loader):
        out = await handle({"code": "I25"}, MagicMock())

    assert out["in_catalog"] is True  # prefix has children
    assert out["assignable"] is False
    assert out["name"] == "(category) 循环系统疾病"
    assert out["chapter"] == "第9章 循环系统疾病"
    assert out["parent_hierarchy"] == ["9", "I25", "I25"]
    # Children listed (top 20, sorted by code)
    assert len(out["children_if_non_assignable"]) == 3
    child_codes = [c["code"] for c in out["children_if_non_assignable"]]
    assert child_codes == ["I25.10", "I25.110", "I25.5"]


# ── unknown code ─────────────────────────────────────────────────────


async def test_verify_code_unknown_code_no_children():
    """Unknown code with no children → in_catalog=False, all fields empty."""
    from app.icoder.mcp.handlers.verify_code import handle

    loader = MagicMock()
    loader.has = MagicMock(return_value=False)
    loader.all_codes = MagicMock(return_value=[])  # no children

    with patch("app.services.icd10cn_loader.get_loader", return_value=loader):
        out = await handle({"code": "X99.999"}, MagicMock())

    assert out["in_catalog"] is False
    assert out["assignable"] is False
    assert out["name"] == ""
    assert out["chapter"] == ""
    assert out["parent_hierarchy"] == []
    assert out["children_if_non_assignable"] == []


# ── aliases cap at 10 ────────────────────────────────────────────────


async def test_verify_code_aliases_capped_at_10():
    """When the catalog has 15 synonyms, only the first 10 are returned."""
    from app.icoder.mcp.handlers.verify_code import handle

    syns = tuple(f"synonym_{i}" for i in range(15))
    entry = _make_entry(synonyms_cn=syns)
    loader = MagicMock()
    loader.has = MagicMock(return_value=True)
    loader.get = MagicMock(return_value=entry)
    loader.chapter_for = MagicMock(return_value="第9章")
    loader.all_codes = MagicMock(return_value=[entry])

    with patch("app.services.icd10cn_loader.get_loader", return_value=loader):
        out = await handle({"code": "I50.900"}, MagicMock())

    assert len(out["aliases"]) == 10
    assert out["aliases"] == list(syns[:10])


# ── children sort by code ────────────────────────────────────────────


async def test_verify_code_children_sorted_by_code():
    """Children list is sorted alphabetically by code (deterministic)."""
    from app.icoder.mcp.handlers.verify_code import handle

    # Out-of-order children
    c1 = _make_entry(code="I25.5", name_cn="慢性缺血性心脏病")
    c2 = _make_entry(code="I25.10", name_cn="动脉粥样硬化性心脏病")
    c3 = _make_entry(code="I25.110", name_cn="粥样硬化性心脏病")

    loader = MagicMock()
    loader.has = MagicMock(return_value=False)
    loader.get = MagicMock(return_value=c2)
    loader.chapter_for = MagicMock(return_value="第9章")
    loader.all_codes = MagicMock(return_value=[c1, c2, c3])  # unsorted

    with patch("app.services.icd10cn_loader.get_loader", return_value=loader):
        out = await handle({"code": "I25"}, MagicMock())

    child_codes = [c["code"] for c in out["children_if_non_assignable"]]
    # Sorted lexicographically — "I25.10" < "I25.110" < "I25.5"
    assert child_codes == ["I25.10", "I25.110", "I25.5"]


# ── empty code input ─────────────────────────────────────────────────


async def test_verify_code_empty_code_returns_in_catalog_false():
    """Empty code string → in_catalog=False, no crash."""
    from app.icoder.mcp.handlers.verify_code import handle

    loader = MagicMock()
    loader.has = MagicMock(return_value=False)
    loader.all_codes = MagicMock(return_value=[])

    with patch("app.services.icd10cn_loader.get_loader", return_value=loader):
        out = await handle({"code": ""}, MagicMock())

    assert out["code"] == ""
    assert out["in_catalog"] is False
    assert out["assignable"] is False


# ── loader unavailable ───────────────────────────────────────────────


async def test_verify_code_loader_unavailable_returns_empty():
    """When icd10cn_loader raises (asset dir not mounted), return empty envelope."""
    from app.icoder.mcp.handlers.verify_code import handle

    with patch(
        "app.services.icd10cn_loader.get_loader",
        side_effect=RuntimeError("asset dir not mounted"),
    ):
        out = await handle({"code": "I50.900"}, MagicMock())

    assert out["in_catalog"] is False
    assert out["assignable"] is False
    assert out["name"] == ""
    assert out["chapter"] == ""
