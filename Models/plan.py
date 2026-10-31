from beanie import Document
from pydantic import Field
from datetime import datetime
from typing import Optional, List
from uuid import UUID, uuid4
import enum


class SupportTier(str, enum.Enum):
    """Support tier enumeration"""
    community = "community"
    email = "email"
    priority = "priority"
    dedicated = "dedicated"


class Plan(Document):
    """Pricing Plan model"""
    
    # ID and timestamps
    id: UUID = Field(default_factory=uuid4, alias="_id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Basic Information
    name: str = Field(..., max_length=100)
    slug: str = Field(..., max_length=50, unique=True)
    description: Optional[str] = None
    
    # Pricing (in cents) - Monthly and Yearly for each region
    price_monthly_usd: int = Field(default=0)
    price_yearly_usd: int = Field(default=0)
    price_monthly_gbp: int = Field(default=0)
    price_yearly_gbp: int = Field(default=0)
    price_monthly_eur: int = Field(default=0)
    price_yearly_eur: int = Field(default=0)
    price_monthly_inr: int = Field(default=0)
    price_yearly_inr: int = Field(default=0)
    
    # Limits
    max_employees: int = Field(default=-1)  # -1 = unlimited
    max_admin_users: int = Field(default=1)
    
    # Features
    modules_json: dict = Field(default_factory=dict)
    api_access: bool = Field(default=False)
    sso_enabled: bool = Field(default=False)
    white_label: bool = Field(default=False)
    
    # Support & Trial
    support_tier: SupportTier = Field(default=SupportTier.community)
    has_trial: bool = Field(default=True)
    trial_days: int = Field(default=14)
    
    # Regions
    regions_allowed: List[str] = Field(default_factory=lambda: ["US"])
    
    # Status & Display
    is_active: bool = Field(default=True)
    sort_order: int = Field(default=0)
    
    class Settings:
        name = "plans"
        indexes = [
            "slug",
            "is_active",
        ]
    
    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v)
        }
    
    def __repr__(self):
        return f"<Plan {self.name} ({self.slug})>"
