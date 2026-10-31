from beanie import Document
from pydantic import Field, EmailStr
from datetime import datetime
from typing import Optional, Literal
from uuid import UUID, uuid4
import enum


class DealContactRole(str, enum.Enum):
    primary_contact = "primary_contact"
    decision_maker = "decision_maker"
    influencer = "influencer"
    evaluator = "evaluator"
    finance_approver = "finance_approver"
    legal_approver = "legal_approver"
    technical_contact = "technical_contact"
    other = "other"


class DealTeamRole(str, enum.Enum):
    sales_owner = "sales_owner"
    sales_manager = "sales_manager"
    solution_consultant = "solution_consultant"
    implementation_consultant = "implementation_consultant"
    csm = "csm"


class CrmDealContact(Document):
    """Association between a Deal and a Contact (supports multiple contacts per deal)"""
    id: UUID = Field(default_factory=uuid4, alias="_id")
    deal_id: UUID
    tenant_id: UUID
    contact_id: Optional[UUID] = None  # FK to crm_contacts (optional if manual)

    # Denormalized for performance (copied from contact on association)
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    job_title: Optional[str] = None
    linkedin_url: Optional[str] = None
    company_name: Optional[str] = None

    role: DealContactRole = Field(default=DealContactRole.primary_contact)
    is_primary: bool = Field(default=False)
    notes: Optional[str] = None

    created_by: Optional[UUID] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "crm_deal_contacts"
        indexes = ["deal_id", "tenant_id", "contact_id", "is_primary"]


class CrmDealTeam(Document):
    """Internal team members working on a deal"""
    id: UUID = Field(default_factory=uuid4, alias="_id")
    deal_id: UUID
    tenant_id: UUID
    user_id: UUID  # FK to users

    # Denormalized
    user_name: Optional[str] = None
    user_email: Optional[str] = None

    role: DealTeamRole = Field(default=DealTeamRole.sales_owner)

    added_by: Optional[UUID] = None
    added_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "crm_deal_team"
        indexes = ["deal_id", "tenant_id", "user_id"]


class CrmDealLineItem(Document):
    """Product / line item associated with a deal"""
    id: UUID = Field(default_factory=uuid4, alias="_id")
    deal_id: UUID
    tenant_id: UUID

    product_name: str = Field(..., max_length=200)
    product_id: Optional[UUID] = None  # FK to future CrmProduct model
    description: Optional[str] = None

    quantity: float = Field(default=1.0, ge=0)
    unit_price: float = Field(default=0.0, ge=0)
    discount_pct: float = Field(default=0.0, ge=0, le=100)
    tax_pct: float = Field(default=0.0, ge=0, le=100)
    total: float = Field(default=0.0)  # Auto-calculated

    sort_order: int = Field(default=0)

    created_by: Optional[UUID] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "crm_deal_line_items"
        indexes = ["deal_id", "tenant_id"]

    def calculate_total(self) -> float:
        """Calculate line item total: (qty * unit_price) - discount + tax"""
        subtotal = self.quantity * self.unit_price
        after_discount = subtotal * (1 - self.discount_pct / 100)
        with_tax = after_discount * (1 + self.tax_pct / 100)
        return round(with_tax, 2)
