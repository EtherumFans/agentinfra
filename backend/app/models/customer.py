# iCoDer — Customer model for Corti parity (Embedded Assistant end-user mgmt).
#
# Corti /customers IA: Name / NFR / Region / Customer ID / Created / Actions.
# iCoDer-side mapping: a Customer is a hospital/tenant's downstream
# end-user (the patient-clinician conversation context), surfaced by the
# Embedded Assistant Web Component. Region is one of {us, eu, cn} —
# Corti has US/EU; iCoDer adds CN since Cloud SaaS serves 中国医院.
import enum
from sqlalchemy import String, Enum, Integer, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.models.base import TimestampMixin


class CustomerRegion(str, enum.Enum):
    US = "us"
    EU = "eu"
    CN = "cn"


class Customer(Base, TimestampMixin):
    """A downstream end-user surfaced via Embedded Assistant.

    customer_id is the public-facing stable ID of form ``{tenant_slug}/{suffix}``
    (e.g. ``songluhua/clinic-a``). The leading ``{tenant_slug}/`` is the org
    identifier; the trailing ``suffix`` is editable on creation. Together they
    form a globally-unique handle.
    """

    __tablename__ = "customers"
    __table_args__ = (
        Index("ix_customers_org_id", "organization_id"),
        Index("ix_customers_customer_id", "customer_id", unique=True),
    )

    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id"), nullable=False
    )
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    customer_id: Mapped[str] = mapped_column(String(128), nullable=False)
    region: Mapped[CustomerRegion] = mapped_column(
        Enum(CustomerRegion), default=CustomerRegion.CN, nullable=False
    )
    # NFR — "Notes (Filled Records)" surfaced in the Corti list table.
    # It is the count of clinical notes / encounters this customer has
    # ingested via Embedded Assistant. iCoDer keeps this as a denormalized
    # counter; the writer increments it from the Embedded runtime hook.
    nfr: Mapped[int] = mapped_column(Integer, default=0, nullable=False)