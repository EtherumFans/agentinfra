# iCoDer — Template model for Corti parity (Templates Beta page).
#
# Corti /templates IA: Manage templates and sections for generating
# structured documents. Each template is a reusable prompt + structure
# that drives Text Generation or Document generation. Templates have:
#   - name + description (display)
#   - content (the prompt + structure payload, kept as text for now)
#   - category (住院 / 手术 / 门诊 / 急诊 / 自定义) — iCoDer-Chinese
#     extension of Corti's clinical-note categories
#   - language (zh-CN / en-US)
#   - is_builtin (Corti "Corti template" badge) vs custom (user-created)
#   - scope ("all_customers" default; per-tenant or single-customer later)
#
# iCoDer extension: a CN-friendly category taxonomy is exposed; the
# `language` field defaults to zh-CN since Cloud SaaS serves 中国医院.
import enum
from sqlalchemy import String, Enum, Boolean, ForeignKey, Text, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.models.base import TimestampMixin


class TemplateCategory(str, enum.Enum):
    INPATIENT = "inpatient"      # 住院
    SURGERY = "surgery"          # 手术
    OUTPATIENT = "outpatient"    # 门诊
    EMERGENCY = "emergency"      # 急诊
    CONSULTATION = "consultation"  # 会诊
    CUSTOM = "custom"            # 自定义


class TemplateLanguage(str, enum.Enum):
    ZH_CN = "zh-CN"
    EN_US = "en-US"


class TemplateScope(str, enum.Enum):
    ALL_CUSTOMERS = "all_customers"
    SINGLE_CUSTOMER = "single_customer"


class Template(Base, TimestampMixin):
    """A reusable content template surfaced via the Templates page.

    Built-in templates are seeded once at startup; custom templates
    are user-created via the Template builder modal.
    """

    __tablename__ = "templates"
    __table_args__ = (
        Index("ix_templates_org_id", "organization_id"),
        Index("ix_templates_category", "category"),
    )

    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(String(1024), default="", nullable=False)
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    category: Mapped[TemplateCategory] = mapped_column(
        Enum(TemplateCategory), default=TemplateCategory.CUSTOM, nullable=False
    )
    language: Mapped[TemplateLanguage] = mapped_column(
        Enum(TemplateLanguage), default=TemplateLanguage.ZH_CN, nullable=False
    )
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    scope: Mapped[TemplateScope] = mapped_column(
        Enum(TemplateScope), default=TemplateScope.ALL_CUSTOMERS, nullable=False
    )