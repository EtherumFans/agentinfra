"""PHI redactor (SPEC §6.3).

Wraps simple rule-based PHI/PII detection and replaces with spec tags
``<REDACTED:NAME>`` / ``<REDACTED:ID_CARD>`` / ``<REDACTED:PHONE>`` /
``<REDACTED:ADDRESS>`` / ``<REDACTED:EMAIL>`` /
``<REDACTED:MEDICAL_RECORD_NO>`` / ``<REDACTED:INSURANCE_NO>``.

This is intentionally simple rule-based redaction (mirrors the existing
``backend/icoder_runtime/core/pii_redaction.py``) — production-grade
medical de-identification is Phase 5 work. The Orchestrator uses it as
a hard first step; ``phi_redactor.redact`` failure raises
``OrchestratorError`` with code ``PHI_REDACTION_FAILED`` and stage ``received``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .errors import OrchestratorError


# ---------------------------------------------------------------------------
# Pattern catalogue — (entity_type, regex)
# ---------------------------------------------------------------------------
# Replacement = ``<REDACTED:TYPE>``. Order matters: longest/most-specific
# patterns first (address before phone, ID card before bank card).

_PHI_PATTERNS: tuple[tuple[str, str], ...] = (
    # ID card — 18 digits, GB 11643-1999 layout
    ("ID_CARD", r"[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]"),
    # Phone (mobile + landline)
    ("PHONE", r"1[3-9]\d{9}"),
    ("PHONE", r"0\d{2,3}[-\s]?\d{7,8}"),
    # Address (province/city/district) — captured as a unit
    (
        "ADDRESS",
        r"(北京市|天津市|上海市|重庆市|河北省|山西省|辽宁省|吉林省|黑龙江省|江苏省|浙江省|"
        r"安徽省|福建省|江西省|山东省|河南省|湖北省|湖南省|广东省|海南省|四川省|贵州省|"
        r"云南省|陕西省|甘肃省|青海省|台湾省|内蒙古自治区|广西壮族自治区|西藏自治区|"
        r"宁夏回族自治区|新疆维吾尔自治区)"
        r"[一-龥]{0,15}(?:市|区|县|镇|乡|街道|路|村|号|弄|巷|楼|栋|单元|室|层)",
    ),
    ("ADDRESS", r"[一-龥]{2,10}(?:路|街|巷|弄|道)[一-龥\d\s]{0,20}(?:号|弄)"),
    # Medical record numbers — labeled or bare
    (
        "MEDICAL_RECORD_NO",
        r"(?P<label>(?:病案号|住院号|门诊号|病历号|登记号|就诊号|入院号)[:：\s]*)[\dA-Za-z\-]+",
    ),
    # Insurance/member number — keep the label so governed field parsers can
    # still identify the redacted value without receiving the identifier.
    (
        "INSURANCE_NO",
        r"(?P<label>(?:医保号|社保号|参保号|参保编号|参保人编号|保险会员号)[:：\s]*)[A-Za-z0-9\-]+",
    ),
    # Date of birth and provider identifiers are preserved only as typed
    # placeholders; their structural labels remain available to local Agents.
    (
        "DATE_OF_BIRTH",
        r"(?P<label>(?:出生日期|出生年月)[:：\s]*)\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2}日?",
    ),
    (
        "PROVIDER_ID",
        r"(?P<label>(?:医师执业编号|医师编号|NPI)[:：\s]*)[A-Za-z0-9\-]+",
    ),
    # Bank card (16-19 digits) — bare
    ("BANK_CARD", r"\b\d{16,19}\b"),
    # Email
    ("EMAIL", r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
)

# Chinese surnames (top 100, single character) — for name detection
_SURNAMES = (
    "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜"
    "戚谢邹喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳鲍史唐费"
    "廉岑薛雷贺倪汤滕殷罗毕郝邬安常乐于时傅皮齐康伍余元卜顾孟平黄和穆萧"
    "尹姚邵湛汪祁毛禹狄米贝明臧计伏成戴谈宋茅庞熊纪舒屈项祝董梁杜阮蓝"
    "闵席季麻强贾路娄危江童颜郭梅盛林刁钟徐邱骆高夏蔡田樊胡凌霍虞万支"
    "柯管卢莫经房裘干解应宗丁宣贲邓郁单杭洪包诸左石崔吉钮龚程邢裴陆荣翁"
    "荀羊於惠甄曲家封芮储靳汲糜松井段富巫乌焦巴弓牧山谷车侯宓蓬全郗班仰"
    "秋仲伊宫宁仇栾暴甘戎祖武符刘景詹束龙叶幸司韶郜黎薄印白怀蒲从鄂索咸"
    "籍赖卓蔺屠蒙池乔阴胥能苍双闻莘党翟谭贡劳姬申扶堵冉宰雍桑桂濮牛寿通"
    "边扈燕冀浦尚农温别庄晏柴阎充慕连茹习艾鱼容向古易慎戈廖终暨居衡步都"
    "耿满弘匡国文寇广阙东欧沃利蔚越隆师巩聂晁勾敖融冷辛阚那简饶空曾毋沙"
    "养鞠须丰巢关相查后荆红游竺权盖益桓公"
)

# 2-3 character Chinese name: <surname> + 1 or 2 given-name chars.
# We deliberately do NOT anchor at the right boundary with a Chinese-char
# lookahead — names in Chinese text are followed by verbs/nouns that are also
# Chinese (e.g. "张三丰入院"). We accept some over-redaction (compound
# surname + 2-char phrases that happen to match) as the cost of rule-based
# MVP. Phase 5 swaps to a certified de-identification service.
_NAME_RE = re.compile(rf"(?<![一-龥])[{_SURNAMES}][一-龥]{{1,2}}")
_LABELED_NAME_RE = re.compile(
    rf"(?P<label>(?:患者姓名|姓名)[:：\s]*|患者)(?P<name>[{_SURNAMES}][一-龥]{{1,2}})"
)

# High-frequency Chinese clinical phrases that satisfy the intentionally
# broad surname+1/2-character MVP name regex.  Protect only complete,
# confirmed medical terms while NAME detection runs; real names are still
# redacted by the same regex.  This prevents loss of clinically material
# facts such as laterality, normal examination, ECG morphology, and common
# diagnoses before CDI reasoning begins.
_CLINICAL_NAME_FALSE_POSITIVES: tuple[str, ...] = (
    "左侧肋骨", "右侧肋骨", "左侧肢体", "右侧肢体",
    "查体正常", "双肺清晰", "双肺底", "窦性心律", "左室射血分数",
    "ST段抬高", "段抬高", "高血压", "高脂血症", "利尿治疗",
    "单纯性", "阴性",
    # Surgical/anesthesia facts. ``全`` is a real surname, so the broad MVP
    # name regex otherwise turns ``全麻下`` into a NAME redaction and destroys
    # a clinically material registry field before the Agent sees it.
    "全麻状态下", "全麻下", "全麻手术", "全身麻醉",
    "静吸复合全麻", "椎管内麻醉", "硬膜外麻醉",
    "腰麻", "局部麻醉", "局麻", "神经阻滞麻醉", "静脉麻醉",
    # Prior-authorization structural labels and common documented phrases.
    # The broad surname detector otherwise treats their first 2-3 characters
    # as a person name and destroys the label before governed parsing.
    "申请医师资质", "申请医师", "支付政策编号", "支付政策版本",
    "支付方要求", "支付政策", "支付方", "申请类型", "申请药品",
    "申请项目", "申请服务", "申请原因", "申请目的", "皮下注射",
    "继续使用",
    # Claim/billing structural labels.  ``申`` and ``金`` are surnames, so the
    # intentionally broad MVP name matcher would otherwise corrupt
    # ``申报总金额`` across the route + handler double-redaction boundary.
    "申报总金额", "申报金额", "申报总额", "结算金额",
    # Denial-appeal structural labels and workflow terms. ``申``/``经`` are
    # surnames, so the broad MVP matcher otherwise destroys labels before the
    # governed denial parser sees them. These are fixed workflow vocabulary,
    # not patient or clinician names.
    "申诉截止日期", "申诉层级", "申诉渠道", "申诉方联系方式",
    "申诉金额", "申诉请求", "申诉路径", "申诉机构", "申诉医师",
    "经治医师", "经办机构", "处理路径", "支付类型", "医保类型",
    "支付方通知记录", "拟申诉诊断", "拟申诉手术", "拟申诉项目",
    "金额", "申诉并附临床文档", "申诉", "更正申报", "请求人工复核",
    # Clinical education wording. ``应`` is a surname, so the broad MVP
    # detector otherwise corrupts ordinary directives such as ``应立即启动``
    # before exact-span source binding runs.
    "应立即",
)


def _replacement(entity_type: str) -> str:
    return f"<REDACTED:{entity_type}>"


@dataclass
class PHIRedactionResult:
    """Outcome of a single ``PHIRedactor.redact`` call."""

    redacted_text: str
    entity_types: list[str] = field(default_factory=list)
    entity_counts: dict[str, int] = field(default_factory=dict)
    redaction_applied: bool = False

    def to_dict(self) -> dict:
        return {
            "redacted_text": self.redacted_text,
            "entity_types": list(self.entity_types),
            "entity_counts": dict(self.entity_counts),
            "redaction_applied": self.redaction_applied,
        }


@dataclass
class PHIPayloadRedactionResult:
    """Outcome of recursively redacting a JSON-like payload.

    Object keys are preserved because changing them would corrupt request
    schemas. Every string value is redacted before the payload crosses the
    runtime boundary.
    """

    value: Any
    entity_types: list[str] = field(default_factory=list)
    entity_counts: dict[str, int] = field(default_factory=dict)
    redaction_applied: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "entity_types": list(self.entity_types),
            "entity_counts": dict(self.entity_counts),
            "redaction_applied": self.redaction_applied,
        }


class PHIRedactionError(OrchestratorError):
    """Raised when redaction itself fails (regex blew up, input is None, etc.)."""

    def __init__(self, message: str, *, stage: str = "received") -> None:
        super().__init__(
            message=message,
            code="phi_redaction_failed",
            stage=stage,
            retryable=False,
        )
        # http_status from A2A_CODES table for PHI_REDACTION_FAILED = 500


class PHIRedactor:
    """Spec-compliant PHI redactor (rule-based).

    Stateless and deterministic — same input ⇒ same output. Phase 1 only;
    swap to a certified medical de-identification service in Phase 5.
    """

    # Patterns excluding NAME — name is applied separately as a post-pass
    # because we want to count NAME separately from labeled fields.
    _LABELED_PATTERNS: tuple[tuple[str, str], ...] = tuple(
        (etype, pattern) for etype, pattern in _PHI_PATTERNS
    )

    def redact(self, text: str) -> PHIRedactionResult:
        """Apply PHI redaction. Never returns original PHI.

        Raises ``PHIRedactionError`` on invalid input (None, non-string)
        or internal regex failure. Per spec §6.3, callers must NOT skip
        this step.
        """
        if text is None:
            raise PHIRedactionError("PHI redaction input is None")
        if not isinstance(text, str):
            raise PHIRedactionError(
                f"PHI redaction input must be str, got {type(text).__name__}"
            )

        try:
            return self._redact(text)
        except re.error as e:  # catastrophic backtracking / invalid pattern
            raise PHIRedactionError(f"PHI regex failure: {e}") from e

    def _redact(self, text: str) -> PHIRedactionResult:
        if not text:
            return PHIRedactionResult(redacted_text=text)

        current = text
        counts: dict[str, int] = {}

        # 1) labeled patterns (ID_CARD / PHONE / ADDRESS / etc.)
        for entity_type, pattern in self._LABELED_PATTERNS:
            replacement = _replacement(entity_type)
            compiled = re.compile(pattern)
            matches = list(compiled.finditer(current))
            if matches:
                count = len(matches)
                counts[entity_type] = counts.get(entity_type, 0) + count
                current = compiled.sub(
                    lambda match: (
                        f"{match.groupdict().get('label') or ''}{replacement}"
                    ),
                    current,
                )

        # 2) NAME — applied last so it doesn't strip chars used by other
        #    patterns (e.g. a phone-with-surname typo)
        protected: dict[str, str] = {}
        # Protect longest phrases first so a short prefix such as ``支付方``
        # cannot prevent protection of ``支付方通知记录`` later in the list.
        for index, phrase in enumerate(
            sorted(_CLINICAL_NAME_FALSE_POSITIVES, key=len, reverse=True)
        ):
            if phrase not in current:
                continue
            token = f"__CLINICAL_TERM_{index}__"
            protected[token] = phrase
            current = current.replace(phrase, token)

        labeled_name_matches = list(_LABELED_NAME_RE.finditer(current))
        if labeled_name_matches:
            counts["NAME"] = counts.get("NAME", 0) + len(labeled_name_matches)
            current = _LABELED_NAME_RE.sub(
                lambda match: f"{match.group('label')}<REDACTED:NAME>",
                current,
            )
        name_matches = _NAME_RE.findall(current)
        if name_matches:
            counts["NAME"] = counts.get("NAME", 0) + len(name_matches)
            current = _NAME_RE.sub(_replacement("NAME"), current)

        for token, phrase in protected.items():
            current = current.replace(token, phrase)

        entity_types = sorted(counts.keys())
        return PHIRedactionResult(
            redacted_text=current,
            entity_types=entity_types,
            entity_counts=counts,
            redaction_applied=bool(entity_types),
        )


def redact_payload(
    value: Any,
    *,
    redactor: PHIRedactor | None = None,
    max_depth: int = 16,
    max_nodes: int = 10_000,
) -> PHIPayloadRedactionResult:
    """Recursively redact every string value in a JSON-like payload.

    The traversal is deliberately bounded and fails closed. Unsupported
    runtime objects are rejected instead of being stringified because their
    representation could disclose PHI or secrets.
    """
    if max_depth < 0:
        raise PHIRedactionError("PHI payload max_depth must be non-negative")
    if max_nodes < 1:
        raise PHIRedactionError("PHI payload max_nodes must be positive")

    active_redactor = redactor or PHIRedactor()
    counts: dict[str, int] = {}
    visited = 0

    def _merge(result: PHIRedactionResult) -> None:
        for entity_type, count in result.entity_counts.items():
            counts[entity_type] = counts.get(entity_type, 0) + count

    def _walk(item: Any, depth: int) -> Any:
        nonlocal visited
        visited += 1
        if visited > max_nodes:
            raise PHIRedactionError("PHI payload exceeds maximum node count")
        if depth > max_depth:
            raise PHIRedactionError("PHI payload exceeds maximum depth")

        if isinstance(item, str):
            result = active_redactor.redact(item)
            _merge(result)
            return result.redacted_text
        if item is None or isinstance(item, (bool, int, float)):
            return item
        if isinstance(item, dict):
            if not all(isinstance(key, str) for key in item):
                raise PHIRedactionError("PHI payload object keys must be strings")
            return {key: _walk(child, depth + 1) for key, child in item.items()}
        if isinstance(item, list):
            return [_walk(child, depth + 1) for child in item]
        if isinstance(item, tuple):
            return tuple(_walk(child, depth + 1) for child in item)
        raise PHIRedactionError(
            f"PHI payload contains unsupported type {type(item).__name__}"
        )

    redacted_value = _walk(value, 0)
    entity_types = sorted(counts)
    return PHIPayloadRedactionResult(
        value=redacted_value,
        entity_types=entity_types,
        entity_counts=counts,
        redaction_applied=bool(entity_types),
    )


__all__ = [
    "PHIPayloadRedactionResult",
    "PHIRedactionError",
    "PHIRedactionResult",
    "PHIRedactor",
    "redact_payload",
]
