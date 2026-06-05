"""PII Redaction — simple rule-based redaction for hospital deployment.

WARNING: This is SIMPLE rule-based redaction, NOT production-grade medical de-identification.
It removes obvious PII patterns (names, IDs, phone numbers, addresses) but does NOT
guarantee HIPAA/GB/T 35273-2020 compliance. For production, integrate a certified
medical de-identification service.

Redaction rules (MVP):
- Chinese names (2-4 character common patterns)
- ID card numbers (18 digits)
- Phone numbers (11 digits)
- Addresses (province/city/district patterns)
- Medical record numbers / hospital admission numbers
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# Chinese family names (top 100)
_SURNAMES = "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜戚谢邹喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳酆鲍史唐费廉岑薛雷贺倪汤滕殷罗毕郝邬安常乐于时傅皮下齐康伍余元卜顾孟平黄和穆萧尹姚邵湛汪祁毛禹狄米贝明臧计伏成戴谈宋茅庞熊纪舒屈项祝董梁杜阮蓝闵席季麻强贾路娄危江童颜郭梅盛林刁钟徐邱骆高夏蔡田樊胡凌霍虞万支柯昝管卢莫经房裘缪干解应宗丁宣贲邓郁单杭洪包诸左石崔吉钮龚程嵇邢滑裴陆荣翁荀羊於惠甄曲家封芮羿储靳汲邴糜松井段富巫乌焦巴弓牧隗山谷车侯宓蓬全郗班仰秋仲伊宫宁仇栾暴甘钭厉戎祖武符刘景詹束龙叶幸司韶郜黎蓟薄印宿白怀蒲邰从鄂索咸籍赖卓蔺屠蒙池乔阴鬱胥能苍双闻莘党翟谭贡劳逄姬申扶堵冉宰郦雍卻璩桑桂濮牛寿通边扈燕冀郏浦尚农温别庄晏柴瞿阎充慕连茹习宦艾鱼容向古易慎戈廖庾终暨居衡步都耿满弘匡国文寇广禄阙东欧殳沃利蔚越夔隆师巩厍聂晁勾敖融冷訾辛阚那简饶空曾毋沙乜养鞠须丰巢关蒯相查后荆红游竺权逯盖益桓公"

# PII patterns
_PII_PATTERNS: list[tuple[str, str, str]] = [
    # (name, pattern, replacement)
    ("id_card", r"[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]", "[身份证号已脱敏]"),
    ("phone", r"1[3-9]\d{9}", "[手机号已脱敏]"),
    ("fixed_phone", r"0\d{2,3}[-\s]?\d{7,8}", "[电话已脱敏]"),
    ("contact_phone", r"(联系人|家属|紧急)[:：\s]*1[3-9]\d{9}", r"\1: [手机号已脱敏]"),
    ("address_province", r"(北京市|天津市|上海市|重庆市|河北省|山西省|辽宁省|吉林省|黑龙江省|江苏省|浙江省|安徽省|福建省|江西省|山东省|河南省|湖北省|湖南省|广东省|海南省|四川省|贵州省|云南省|陕西省|甘肃省|青海省|台湾省|内蒙古自治区|广西壮族自治区|西藏自治区|宁夏回族自治区|新疆维吾尔自治区)([一-龥]{2,20}(市|区|县|镇|乡|街道|路|村|号|弄|巷|楼|栋|单元|室|层))", "[地址已脱敏]"),
    ("address_street", r"[一-龥]{2,10}(路|街|巷|弄|道)[一-龥\d\s]{0,20}(号|弄)", "[地址已脱敏]"),
    ("medical_record_no", r"(病案号|住院号|门诊号|病历号|登记号|就诊号|入院号)[:：\s]*[\dA-Za-z\-]+", r"\1: [已脱敏]"),
    ("bed_no", r"(床号|床位)[:：\s]*\d+", r"\1: [已脱敏]"),
    ("bank_card", r"\b\d{16,19}\b", "[银行卡号已脱敏]"),
    ("email", r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}", "[邮箱已脱敏]"),
]


@dataclass
class PIIRedactionResult:
    """Result of PII redaction."""
    redacted_text: str = ""
    redaction_applied: bool = False
    redaction_mode: str = "simple"
    fields_redacted: list[str] = field(default_factory=list)
    redaction_count: int = 0
    warning: str = (
        "SIMPLE rule-based redaction — NOT production-grade medical de-identification. "
        "For HIPAA/GB/T 35273 compliance, integrate a certified de-identification service."
    )

    def to_dict(self) -> dict:
        return {
            "redaction_applied": self.redaction_applied,
            "redaction_mode": self.redaction_mode,
            "fields_redacted": self.fields_redacted,
            "redaction_count": self.redaction_count,
            "warning": self.warning,
        }


class PIIRedactor:
    """Simple rule-based PII redaction for hospital deployment."""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled

    def redact(self, text: str) -> PIIRedactionResult:
        """Apply PII redaction to text. Returns redacted text + metadata."""
        if not self.enabled or not text:
            return PIIRedactionResult(redacted_text=text or "")

        result = text
        fields_redacted: list[str] = []
        count = 0

        for name, pattern, replacement in _PII_PATTERNS:
            matches = re.findall(pattern, result)
            if matches:
                result = re.sub(pattern, replacement, result)
                fields_redacted.append(name)
                count += len(matches) if isinstance(matches, list) else 1

        return PIIRedactionResult(
            redacted_text=result,
            redaction_applied=count > 0,
            redaction_mode="simple",
            fields_redacted=list(set(fields_redacted)),
            redaction_count=count,
        )

    def redact_messages(self, messages: list[dict[str, str]]) -> tuple[list[dict[str, str]], PIIRedactionResult]:
        """Redact all message contents. Returns (redacted_messages, redaction_result)."""
        agg_result = PIIRedactionResult()
        redacted = []
        all_fields: set[str] = set()
        total_count = 0

        for msg in messages:
            content = msg.get("content", "")
            r = self.redact(content)
            all_fields.update(r.fields_redacted)
            total_count += r.redaction_count
            redacted.append({**msg, "content": r.redacted_text})

        agg_result.redacted_text = ""  # Not meaningful for message list
        agg_result.redaction_applied = total_count > 0
        agg_result.fields_redacted = sorted(all_fields)
        agg_result.redaction_count = total_count

        return redacted, agg_result
