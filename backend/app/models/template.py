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
import uuid
from datetime import datetime

from sqlalchemy import (
    String, Enum, Boolean, ForeignKey, Text, Index, DateTime, Integer,
    UniqueConstraint, func,
)
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
        Index("ix_templates_deleted_at", "deleted_at"),
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
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )


class TemplateVersion(Base):
    """Immutable, tenant-scoped snapshot created by an explicit publish.

    Draft edits remain on :class:`Template`.  Published rows are intentionally
    append-only: the API exposes only create/read operations and every lookup is
    constrained by both organization and template identifiers.
    """

    __tablename__ = "template_versions"
    __table_args__ = (
        UniqueConstraint(
            "template_id", "version_number", name="uq_template_version_number"
        ),
        Index("ix_template_versions_org_template", "organization_id", "template_id"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id"), nullable=False
    )
    template_id: Mapped[str] = mapped_column(
        ForeignKey("templates.id"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    generation_json: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    published_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
