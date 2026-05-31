# iCoDer - Code Dictionary Service
# ICD-10-CN and ICD-9-CM-3 comprehensive code dictionaries for Chinese hospitals.
import json
import logging
import re
from pathlib import Path
from typing import Optional

from rapidfuzz import fuzz, process

from app.config import settings

logger = logging.getLogger(__name__)


def _load_comprehensive_codes():
    """Load comprehensive ICD-10-CN and ICD-9-CM-3 codes from data module."""
    icd10 = []
    icd9 = []
    try:
        from data.code_dicts.icd_data import ICD10_CN_CODES, ICD9_CM3_CODES, ICD10_CN_CHAPTERS

        for code, name, category in ICD10_CN_CODES:
            # Determine chapter from code prefix
            chapter = ""
            code_prefix = code.split(".")[0] if "." in code else code[:3]
            for ch_range, ch_name in ICD10_CN_CHAPTERS.items():
                start, end = ch_range.split("-")
                if start <= code_prefix <= end:
                    chapter = ch_name
                    break
            icd10.append({
                "code": code,
                "name": name,
                "chapter": chapter,
                "block": category,
            })

        for code, name, category in ICD9_CM3_CODES:
            icd9.append({
                "code": code,
                "name": name,
                "chapter": "",
                "block": category,
            })

        logger.info(
            "Loaded %d ICD-10-CN codes and %d ICD-9-CM-3 codes from comprehensive dataset",
            len(icd10), len(icd9),
        )
    except ImportError as e:
        logger.warning("Failed to load comprehensive code data: %s, using fallback", e)
    return icd10, icd9


_ICD10_CODES, _ICD9_CODES = _load_comprehensive_codes()

# Fallback sample codes in case data module fails to load
if not _ICD10_CODES:
    _ICD10_CODES = [
        {"code": "M80.0", "name": "绝经后骨质疏松伴有病理性骨折", "chapter": "肌肉骨骼系统和结缔组织疾病", "block": "M80 骨质疏松伴有病理性骨折"},
        {"code": "I10.x", "name": "原发性高血压", "chapter": "循环系统疾病", "block": "I10-I15 高血压病"},
        {"code": "E11.9", "name": "2型糖尿病不伴有并发症", "chapter": "内分泌、营养和代谢疾病", "block": "E11 2型糖尿病"},
        {"code": "J44.9", "name": "慢性阻塞性肺病,未特指", "chapter": "呼吸系统疾病", "block": "J44 其他慢性阻塞性肺病"},
        {"code": "I25.1", "name": "动脉硬化性心脏病", "chapter": "循环系统疾病", "block": "I25 慢性缺血性心脏病"},
    ]
if not _ICD9_CODES:
    _ICD9_CODES = [
        {"code": "81.66", "name": "经皮椎体后凸成形术", "chapter": "", "block": "81 关节结构修复术和重建术"},
        {"code": "54.21", "name": "腹腔镜检查", "chapter": "", "block": "54 腹壁和腹膜的手术"},
        {"code": "51.23", "name": "胆囊切除术", "chapter": "", "block": "51 胆囊和胆道的手术"},
        {"code": "45.16", "name": "结肠镜检查", "chapter": "", "block": "45 肠的手术"},
        {"code": "36.07", "name": "冠状动脉药物洗脱支架置入术", "chapter": "", "block": "36 心脏血管的手术"},
    ]


class CodeDictionaryService:
    """Code dictionary search using fuzzy matching and exact lookup.

    Supports: ICD-10-CN (all 22 chapters), ICD-9-CM-3, Insurance codes, Local codes.
    """

    CODE_SYSTEMS = {
        "ICD10_CN": _ICD10_CODES,
        "ICD10_CN_CLINICAL": _ICD10_CODES,
        "ICD9_CM3": _ICD9_CODES,
        "ICD9_CM3_CLINICAL": _ICD9_CODES,
        "INSURANCE_DIAG": _ICD10_CODES,
        "INSURANCE_PROC": _ICD9_CODES,
        "LOCAL": _ICD10_CODES,
    }

    def __init__(self):
        self._ensure_data_files()
        self._codes_cache: dict[str, list[dict]] = {}
        # Build prefix index for faster lookup
        self._prefix_index: dict[str, dict[str, list[int]]] = {}

    def _ensure_data_files(self):
        """Ensure data directories exist."""
        data_dir = Path(settings.DATA_DIR)
        code_dicts_dir = Path(settings.CODE_DICTS_DIR)
        data_dir.mkdir(parents=True, exist_ok=True)
        code_dicts_dir.mkdir(parents=True, exist_ok=True)

    def _get_codes(self, code_system: str) -> list[dict]:
        """Get code list for a system, with caching."""
        if code_system not in self._codes_cache:
            codes = self.CODE_SYSTEMS.get(code_system, _ICD10_CODES)
            self._codes_cache[code_system] = codes
            self._build_prefix_index(code_system, codes)
        return self._codes_cache[code_system]

    def _build_prefix_index(self, code_system: str, codes: list[dict]):
        """Build prefix-based index for fast code lookup."""
        index: dict[str, list[int]] = {}
        for i, c in enumerate(codes):
            code = c["code"].upper()
            # Index by full code
            index.setdefault(code, []).append(i)
            # Index by prefix (for block-level hierarchy)
            prefix = code.split(".")[0] if "." in code else code[:3]
            index.setdefault(f"P:{prefix}", []).append(i)
        self._prefix_index[code_system] = index

    async def search_codes(
        self,
        query: str,
        code_system: str = "ICD10_CN",
        top_k: int = 10,
    ) -> list[dict]:
        """Search codes by name or code using fuzzy matching.

        Searches exact code match first, then exact name match, then fuzzy.
        """
        codes = self._get_codes(code_system)
        q = query.strip()

        # Exact code match first
        q_upper = q.upper()
        for c in codes:
            if c["code"].upper() == q_upper:
                return [{
                    "code": c["code"], "name": c["name"], "score": 1.0,
                    "chapter": c.get("chapter"), "parent_code": c.get("block"),
                    "valid": True,
                }]

        # Prefix code match (e.g., "I10" matches "I10.x")
        prefix_results = []
        for c in codes:
            c_prefix = c["code"].split(".")[0] if "." in c["code"] else c["code"][:3]
            if c_prefix == q_upper:
                prefix_results.append({
                    "code": c["code"], "name": c["name"], "score": 0.95,
                    "chapter": c.get("chapter"), "parent_code": c.get("block"),
                    "valid": True,
                })
        if prefix_results:
            return prefix_results[:top_k]

        # Exact name match
        for c in codes:
            if c["name"] == q:
                return [{
                    "code": c["code"], "name": c["name"], "score": 1.0,
                    "chapter": c.get("chapter"), "parent_code": c.get("block"),
                    "valid": True,
                }]

        # Fuzzy match on name using rapidfuzz
        choices = [(c["name"].lower(), i) for i, c in enumerate(codes)]
        if not choices:
            return []
        results = process.extract(
            q.lower(),
            [c[0] for c in choices],
            scorer=fuzz.partial_ratio,
            limit=min(top_k, len(choices)),
        )
        output = []
        for name, score, idx in results:
            if score < 50:  # Minimum relevance threshold
                continue
            c = codes[idx]
            output.append({
                "code": c["code"],
                "name": c["name"],
                "score": round(score / 100.0, 4),
                "chapter": c.get("chapter"),
                "parent_code": c.get("block"),
                "valid": True,
            })
        return output[:top_k] if output else []

    async def explore_code(self, code: str, code_system: str = "ICD10_CN") -> Optional[dict]:
        """Explore a code's hierarchy — parent, children within same block."""
        codes = self._get_codes(code_system)
        code_upper = code.upper().strip()

        target = None
        for c in codes:
            if c["code"].upper() == code_upper:
                target = c
                break

        if not target:
            return None

        block = target.get("block", "")
        # Extract block code range for parent
        parent = None
        if block:
            parts = block.split()
            if parts and "-" in parts[0]:
                parent = parts[0].split("-")[0]

        # Find siblings in same block
        children = []
        for c in codes:
            if c.get("block") == block and c["code"] != target["code"]:
                children.append({"code": c["code"], "name": c["name"], "level": 1})

        # Find codes that start with target code (more specific)
        subcodes = []
        target_prefix = target["code"].rstrip("x")  # Handle placeholder 'x'
        for c in codes:
            if c["code"] != target["code"] and c["code"].startswith(target_prefix):
                subcodes.append({"code": c["code"], "name": c["name"], "level": 2})

        return {
            "code": target["code"],
            "name": target["name"],
            "code_system": code_system,
            "chapter": target.get("chapter"),
            "block": target.get("block"),
            "parent": parent,
            "children": children[:20],
            "subcodes": subcodes[:20],
            "includes": [],
            "excludes": [],
            "notes": "",
            "valid": True,
        }

    async def get_all_systems(self) -> list[dict]:
        """List available code systems with counts."""
        icd10_count = len(self._get_codes("ICD10_CN"))
        icd9_count = len(self._get_codes("ICD9_CM3"))
        return [
            {"id": "ICD10_CN", "name": "ICD-10-CN 临床版 (2025)", "code_count": icd10_count},
            {"id": "ICD9_CM3", "name": "ICD-9-CM-3 临床版 (2025)", "code_count": icd9_count},
            {"id": "INSURANCE_DIAG", "name": "医保疾病诊断分类与代码", "code_count": icd10_count},
            {"id": "INSURANCE_PROC", "name": "医保手术操作分类与代码", "code_count": icd9_count},
            {"id": "LOCAL", "name": "医院本地扩展码", "code_count": 0},
        ]

    async def validate_code(self, code: str, code_system: str = "ICD10_CN") -> dict:
        """Validate if a code exists in the dictionary."""
        codes = self._get_codes(code_system)
        code_upper = code.upper().strip()
        for c in codes:
            if c["code"].upper() == code_upper:
                return {"valid": True, "code": c["code"], "name": c["name"], "system": code_system}
        return {"valid": False, "code": code, "name": "Unknown", "system": code_system}


    async def lookup_index(self, term: str, code_system: str = "ICD10_CN") -> dict:
        """Simulate flipping through the ICD-10 index for a clinical term.

        iCoDer "Code Like Humans" Step 2: given a term like "骨质疏松",
        returns the main entry + all indented subentries + codes,
        mimicking the hierarchical ICD index structure.

        Returns:
            dict with:
            - main_term: the best matching index entry
            - entries: list of {subterm, code, name, indentation_level}
            - cross_references: See/See also references
            - search_path: the fuzzy search results used
        """
        codes = self._get_codes(code_system)
        q = term.strip()

        # Step 1: Find all codes whose name contains the query term
        matches = []
        for c in codes:
            name_lower = c["name"].lower()
            score = 0.0
            if q.lower() in name_lower:
                score = 0.85
            elif any(part in name_lower for part in q.lower().split()):
                score = 0.70
            else:
                ratio = fuzz.partial_ratio(q.lower(), name_lower)
                if ratio >= 60:
                    score = ratio / 100.0
            if score > 0:
                matches.append({**c, "relevance": score})

        matches.sort(key=lambda x: x["relevance"], reverse=True)

        # Step 2: Build hierarchical index structure
        # Group by chapter for the index tree
        chapters = {}
        for m in matches[:50]:
            ch = m.get("chapter", "Other")
            chapters.setdefault(ch, []).append(m)

        # Build index entries with indentation
        # Level 0: chapter name
        # Level 1: code blocks within chapter
        # Level 2: individual codes
        entries = []
        for chapter_name, chapter_codes in list(chapters.items())[:5]:
            entries.append({
                "term": chapter_name,
                "code": "",
                "name": f"[{chapter_name}]",
                "level": 0,
                "relevance": 1.0,
            })
            blocks = {}
            for c in chapter_codes:
                blk = c.get("block", "")
                blocks.setdefault(blk, []).append(c)

            for block_name, block_codes in blocks.items():
                if block_name:
                    entries.append({
                        "term": block_name,
                        "code": block_codes[0]["code"] if block_codes else "",
                        "name": block_name,
                        "level": 1,
                        "relevance": max(c["relevance"] for c in block_codes),
                    })
                for c in block_codes[:5]:
                    entries.append({
                        "term": c["name"],
                        "code": c["code"],
                        "name": f"{c['code']}  {c['name']}",
                        "level": 2,
                        "relevance": c["relevance"],
                    })

        # Step 3: Cross-references
        # Find codes with related terms (same parent block but different sub-term)
        cross_refs = []
        seen_blocks = set()
        for m in matches[:20]:
            blk = m.get("block", "")
            if blk and blk not in seen_blocks:
                seen_blocks.add(blk)
                siblings = [c for c in codes if c.get("block") == blk and c != m]
                if siblings:
                    cross_refs.append({
                        "from_term": m["name"],
                        "block": blk,
                        "sibling_count": len(siblings),
                        "examples": [s["name"] for s in siblings[:3]],
                    })

        return {
            "main_term": matches[0]["name"] if matches else term,
            "query": term,
            "match_count": len(matches),
            "entries": entries[:60],
            "cross_references": cross_refs[:5],
            "search_path": [{"code": m["code"], "name": m["name"], "relevance": m["relevance"]}
                           for m in matches[:10]],
        }

    async def drill_down(self, code: str, code_system: str = "ICD10_CN",
                         clinical_context: dict = None) -> dict:
        """Drill into a code's subcategories to find the most specific code.

        iCoDer "Code Like Humans" Step 3: given a candidate code like M80,
        checks if more specific subcodes (M80.0, M80.1, ...) better match
        the clinical context.

        Returns:
            dict with:
            - parent_code: the input code
            - sub_codes: list of more specific codes under this parent
            - specificity_gains: what each subcode adds over the parent
            - drill_recommendations: which subcodes to pursue
            - drill_path: hierarchical path from parent to most specific
        """
        codes = self._get_codes(code_system)
        code_upper = code.upper().strip()

        # Normalize code for prefix matching
        code_prefix = code_upper.rstrip("xX").rstrip(".")

        # Find parent code
        parent = None
        for c in codes:
            if c["code"].upper() == code_upper:
                parent = c
                break

        # Find all subcodes (child codes under this parent)
        sub_codes = []
        for c in codes:
            c_code = c["code"].upper()
            if c_code != code_upper and c_code.startswith(code_prefix):
                # Determine specificity level
                depth = len(c_code.split(".")[-1]) if "." in c_code else 0
                sub_codes.append({
                    "code": c["code"],
                    "name": c["name"],
                    "chapter": c.get("chapter", ""),
                    "block": c.get("block", ""),
                    "specificity_depth": depth,
                })

        # Sort by specificity (most specific first)
        sub_codes.sort(key=lambda x: x["specificity_depth"], reverse=True)

        # Calculate specificity gain for each subcode
        gains = []
        if parent and clinical_context:
            parent_name = parent["name"]
            for sc in sub_codes[:15]:
                # What does this subcode add?
                # Extract the differentiating part from the name
                sc_name = sc["name"]
                diff_parts = []
                for part in sc_name.replace(parent_name, "").strip().split("，"):
                    if part.strip():
                        diff_parts.append(part.strip())

                gains.append({
                    "code": sc["code"],
                    "name": sc_name,
                    "specificity_gain": diff_parts if diff_parts else ["more specific variant"],
                })

        # Build drill path (how to navigate from parent to children)
        drill_path = []
        if parent:
            drill_path.append({
                "level": 0,
                "code": parent["code"],
                "name": parent["name"],
                "action": "start",
            })
        for sc in sub_codes[:10]:
            drill_path.append({
                "level": sc["specificity_depth"],
                "code": sc["code"],
                "name": sc["name"],
                "action": "consider_drill",
            })

        return {
            "parent_code": code,
            "parent_name": parent["name"] if parent else "Unknown",
            "chapter": parent.get("chapter", "") if parent else "",
            "sub_code_count": len(sub_codes),
            "sub_codes": sub_codes[:20],
            "specificity_gains": gains[:15],
            "drill_recommendations": [
                {"code": sc["code"], "name": sc["name"]}
                for sc in sub_codes[:5]
            ],
            "drill_path": drill_path,
        }


# Singleton
code_dict_service = CodeDictionaryService()
