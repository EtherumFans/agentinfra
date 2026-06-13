"""GroupingExpert — the DRG/DIP grouping capability (the China-specific wedge Corti lacks).

A thin-but-principled CHS-DRG / DIP grouper that turns a sequenced code set into a route:

  primary dx ──▶ MDC (by ICD-10 chapter)
  + procedure? ─▶ ADRG (surgical vs medical)
  + CC/MCC?   ──▶ DRG (severity tier: 1=MCC / 3=CC / 5=none)
  primary dx ──▶ DIP 病种 + 分值 (score scaled by severity)

This is a *sample* grouper (a handful of ADRG/DIP entries covering the demo encounter);
production binds the院内 DRG 分组器 + 本地 DIP 目录. It is deliberately rule-based and
zero-dependency. It only groups on confirmed ``codes`` — unconfirmed high-risk procedures
sitting in ``candidates`` do NOT pull the case into a surgical ADRG (that gap is what the
drg_dip ruleset flags).
"""
from __future__ import annotations

from ..runtime.types import CodeResult, DrgRoute

# MDC by ICD-10 chapter/prefix (longest prefix wins, so Z51 beats a bare Z).
_MDC: list[tuple[str, tuple[str, str]]] = sorted(
    [
        ("Z51", ("MDCR", "骨髓增生疾病和功能障碍、低分化恶性肿瘤、化疗")),
        ("I", ("MDCF", "循环系统疾病及功能障碍")),
        ("J", ("MDCE", "呼吸系统疾病及功能障碍")),
        ("N", ("MDCL", "肾及泌尿系统疾病及功能障碍")),
        ("E", ("MDCK", "内分泌、营养、代谢疾病及功能障碍")),
        ("M", ("MDCI", "肌肉骨骼系统及结缔组织疾病及功能障碍")),
    ],
    key=lambda kv: len(kv[0]),
    reverse=True,
)

# Medical ADRG by primary-diagnosis prefix.
_ADRG_MED: list[tuple[str, tuple[str, str]]] = sorted(
    [
        ("I50", ("FT2", "心力衰竭、休克")),
        ("I48", ("FU2", "心律失常及传导障碍")),
        ("I10", ("FT4", "高血压")),
        ("I66", ("BR2", "脑缺血性疾患")),
        ("J18", ("ES3", "呼吸系统感染/炎症")),
        ("J98", ("ES1", "呼吸系统其他疾患")),
        ("N18", ("LL1", "肾功能不全")),
        ("E11", ("KS1", "糖尿病")),
        ("M80", ("IU1", "骨病及特定关节病")),
        ("Z51", ("RE1", "恶性增殖性疾患的化学和/或靶向、生物治疗")),
    ],
    key=lambda kv: len(kv[0]),
    reverse=True,
)

# Surgical/operative ADRG by procedure prefix (when a procedure is confirmed in codes).
_ADRG_SURG: list[tuple[str, tuple[str, str]]] = sorted(
    [
        ("45.16", ("GK3", "胃肠镜诊断及治疗操作")),
        ("45.13", ("GK3", "胃肠镜诊断及治疗操作")),
    ],
    key=lambda kv: len(kv[0]),
    reverse=True,
)

# Comorbidity/complication classification (drives the DRG severity tier).
_MCC: set[str] = {"N18.500"}                       # 重度: 尿毒症/CKD5
_CC: set[str] = {                                  # 一般: 常见合并症/并发症
    "N18.900", "I48.x00", "I10.x00", "E11.900", "J18.900", "M80.900", "I66.901",
}

# Sample DIP 病种目录 (primary -> 病种 + 基础分值).
_DIP: dict[str, tuple[str, str, float]] = {
    "I50.900": ("DIP-I50.900", "慢性心力衰竭（内科保守治疗）", 285.0),
    "J18.900": ("DIP-J18.900", "肺炎（内科）", 162.0),
    "N18.900": ("DIP-N18.900", "慢性肾脏病（内科）", 240.0),
    "E11.900": ("DIP-E11.900", "2型糖尿病（内科）", 150.0),
    "I48.x00": ("DIP-I48.x00", "心房颤动（内科）", 178.0),
    "M80.900": ("DIP-M80.900", "骨质疏松性骨折（保守治疗）", 210.0),
    "Z51.102": ("DIP-Z51.102", "恶性肿瘤维持性化学治疗", 95.0),
}

_TIER = {"MCC": ("1", "，伴严重并发症或合并症"), "CC": ("3", "，伴并发症或合并症"), None: ("5", "，不伴并发症或合并症")}
_SCORE_FACTOR = {"MCC": 1.30, "CC": 1.15, None: 1.0}


def _lookup(table: list[tuple[str, tuple[str, str]]], code: str) -> tuple[str, str] | None:
    for prefix, val in table:
        if code.startswith(prefix):
            return val
    return None


class GroupingExpert:
    """DRG/DIP grouping expert. Exposes per-dimension tools + a top-level group()."""

    id = "grouping-expert"

    # --- tools (each is a discrete, observable call) ---
    def mdc_of(self, code: str) -> tuple[str, str] | None:
        return _lookup(_MDC, code)

    def adrg_of(self, primary_code: str, surgical: bool, procedure_code: str | None = None):
        if surgical and procedure_code:
            return _lookup(_ADRG_SURG, procedure_code) or ("GZ1", "其他手术/操作")
        return _lookup(_ADRG_MED, primary_code)

    def cc_level(self, code: str) -> str | None:
        if code in _MCC:
            return "MCC"
        if code in _CC:
            return "CC"
        return None

    def dip_of(self, code: str) -> dict | None:
        e = _DIP.get(code)
        if not e:
            return None
        return {"dip_code": e[0], "dip_name": e[1], "base_score": e[2]}

    # --- top-level grouping ---
    def group(
        self,
        primary: CodeResult | None,
        secondaries: list[CodeResult],
        procedures: list[CodeResult],
    ) -> DrgRoute:
        if primary is None:
            return DrgRoute(
                note="无主要诊断，未进入 DRG/DIP 分组",
                rationale=["缺主要诊断，无法确定 MDC"],
            )

        rationale: list[str] = []
        mdc = self.mdc_of(primary.code)
        mdc_code, mdc_name = (mdc or (None, None))
        rationale.append(
            f"MDC：主诊断 {primary.code} → {mdc_code or '未命中'} {mdc_name or ''}".rstrip()
        )

        surgical = bool(procedures)
        proc_code = procedures[0].code if procedures else None
        adrg = self.adrg_of(primary.code, surgical, proc_code)
        if surgical:
            rationale.append(f"ADRG：确认手术 {proc_code} → 外科组 {adrg[0] if adrg else '未命中'}")
        else:
            rationale.append(f"ADRG：无确认手术 → 内科组 {adrg[0] if adrg else '未命中'}")

        # severity tier from the most severe confirmed comorbidity/complication
        level: str | None = None
        driver: str | None = None
        for c in secondaries:
            lv = self.cc_level(c.code)
            if lv == "MCC":
                level, driver = "MCC", c.code
                break
            if lv == "CC" and level is None:
                level, driver = "CC", c.code
        suffix, tier_label = _TIER[level]
        if level:
            rationale.append(f"严重度：合并症/并发症 {driver}（{level}）→ DRG 严重度 tier {suffix}")
        else:
            rationale.append("严重度：无 CC/MCC → DRG 严重度 tier 5")

        if adrg is None:
            route = DrgRoute(
                adrg=None, drg=None, group_name=None,
                mdc=mdc_code, mdc_name=mdc_name, surgical=surgical, cc_mcc=level,
                note=f"主诊断 {primary.code} 未命中示例 ADRG 表",
                rationale=rationale,
            )
        else:
            adrg_code, adrg_name = adrg
            route = DrgRoute(
                adrg=adrg_code, drg=f"{adrg_code}{suffix}", group_name=adrg_name,
                mdc=mdc_code, mdc_name=mdc_name, surgical=surgical, cc_mcc=level,
                note="示例分组；真实分组依赖院内 DRG 分组器",
                rationale=rationale,
            )

        dip = self.dip_of(primary.code)
        if dip:
            score = round(dip["base_score"] * _SCORE_FACTOR[level], 1)
            route.dip_code = dip["dip_code"]
            route.dip_name = dip["dip_name"]
            route.dip_score = score
            rationale.append(
                f"DIP：{dip['dip_code']} {dip['dip_name']}，基础分值 {dip['base_score']} × "
                f"{_SCORE_FACTOR[level]} = {score}"
            )
        else:
            rationale.append(f"DIP：主诊断 {primary.code} 未命中示例 DIP 目录")

        return route
