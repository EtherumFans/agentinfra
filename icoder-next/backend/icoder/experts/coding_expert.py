"""CodingExpert — the iCoDer analog of Corti's coding-expert.

Exposes the same four tools, over an ICD-10-CN + ICD-9-CM-3 catalog:
  - search     : index retrieval (synonym-aware)
  - verify     : code detail + instructional notes (Includes/Excludes/Code First/Use Additional)
  - guidelines : official coding guideline (mandatory per code)
  - explore    : parent / sibling / child codes

Evidence is located by character offsets (start incl / end excl), never by re-searching
display text downstream — repeated phrases line up wrong with naive indexOf.
"""
from __future__ import annotations

from ..runtime.types import Alternative, CodeNote, Evidence
from .catalog import CATALOG, SAMPLE_CODES, lexicon as catalog_lexicon


class CodingExpert:
    id = "coding-expert"

    def lexicon(self) -> list[str]:
        return catalog_lexicon()

    # --- Tool 1: Search (index retrieval) ---
    def search(self, term: str) -> list[dict]:
        hits = []
        for code, entry in CATALOG.items():
            score = self._match_score(term, entry)
            if score > 0:
                # Verified curated mappings dominate raw national-catalog string matches:
                # over 51k codes, naive string search drifts to near-duplicate siblings
                # (I50.900 -> I50.908) or wrong procedures (45.16 活检 -> 45.13 检查). The
                # boost (> any base score) keeps the demo deterministic with the real catalog
                # overlaid, while non-curated terms still retrieve the national breadth.
                if code in SAMPLE_CODES:
                    score += 1.0
                hits.append(
                    {"code": code, "display": entry["display"], "system": entry["system"], "score": score}
                )
        hits.sort(key=lambda h: (h["score"], h["code"]), reverse=True)
        return hits

    @staticmethod
    def _match_score(term: str, entry: dict) -> float:
        if term == entry["display"]:
            return 1.0
        best = 0.0
        for syn in entry["synonyms"]:
            if term == syn:
                best = max(best, 0.95)
            elif syn and (syn in term or term in syn):
                best = max(best, 0.8)
        return best

    # --- Tool 2: Verify (code detail + instructional notes) ---
    def verify(self, code: str) -> dict | None:
        entry = CATALOG.get(code)
        if not entry:
            return None
        return {
            "code": code,
            "display": entry["display"],
            "system": entry["system"],
            "code_type": entry["code_type"],
            "high_risk": entry.get("high_risk", False),
            "notes": [CodeNote(kind=kind, text=text) for kind, text in entry.get("notes", [])],
        }

    # --- Tool 3: Guidelines (mandatory per code) ---
    def guidelines(self, code: str) -> dict | None:
        entry = CATALOG.get(code)
        if not entry:
            return None
        return {"code": code, "guideline": entry.get("guideline", "")}

    # --- Tool 4: Explore (parent / sibling / child) ---
    def explore(self, code: str) -> dict | None:
        entry = CATALOG.get(code)
        if not entry:
            return None
        return {
            "code": code,
            "parent": entry.get("parent"),
            "siblings": entry.get("siblings", []),
            "children": entry.get("children", []),
        }

    # differentiation hints -> alternatives (≈ 鉴别诊断)
    def alternatives(self, code: str) -> list[Alternative]:
        entry = CATALOG.get(code) or {}
        out: list[Alternative] = []
        for diff in entry.get("differentiation", []):
            out.append(
                Alternative(
                    code=diff["vs"],
                    display=diff.get("vs_display", ""),
                    reason=f'{diff["level"]}: {diff["note"]}',
                )
            )
        return out

    def is_member(self, code: str) -> bool:
        return code in CATALOG

    @staticmethod
    def find_evidences(text: str, term: str, context_index: int = 0) -> list[Evidence]:
        """All non-overlapping char-span occurrences of ``term`` in ``text``."""
        spans: list[Evidence] = []
        start = 0
        while True:
            idx = text.find(term, start)
            if idx == -1:
                break
            spans.append(
                Evidence(context_index=context_index, start=idx, end=idx + len(term), text=term)
            )
            start = idx + len(term)
        return spans
