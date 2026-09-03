# iCoDer - User & Role Models
import enum
from sqlalchemy import String, Enum, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.models.base import TimestampMixin

class UserRole(str, enum.Enum):
    ADMIN = "admin"
    CODER = "coder"  # 编码员
    DEPT_HEAD = "dept_head"  # 科室负责人
    INSURANCE = "insurance"  # 医保办
    QC = "qc"  # 质控科
    CLINICIAN = "clinician"  # 临床医生
    IT = "it"  # 信息科
    # Phase A1D.3 (A1C-B-020) — close 2 of 7 PARTIAL principal mappings.
    # Predecessor state (A1C.4 §3.1): CDI 专员 was conflated with QC;
    # 病案管理员 was conflated with DEPT_HEAD. Both get distinct enum
    # values so RBAC role checks can match Corti-style hospital roles
    # exactly. Migration 030 widens the column type from 7 to 9 allowed
    # literals; no data backfill (existing rows keep their QC / DEPT_HEAD
    # values; new rows opt into the new roles).
    CDI_SPECIALIST = "cdi_specialist"  # CDI 专员
    MEDICAL_RECORDS_ADMIN = "medical_records_admin"  # 病案管理员

class User(Base, TimestampMixin):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(256), nullable=False)
    full_name: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.CODER, nullable=False)
    department: Mapped[str] = mapped_column(String(128), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    token_version: Mapped[int] = mapped_column(default=0, server_default="0")  # Incremented on revoke-tokens
