from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from enum import Enum
from datetime import datetime
import re


class SupportTierEnum(str, Enum):
    """Support tier enumeration"""
    community = "community"
    email = "email"
    priority = "priority"
    dedicated = "dedicated"


class PlanModuleFlags(BaseModel):
    """Module feature flags schema"""
    payroll: Optional[bool] = False
    ats: Optional[bool] = False
    performance: Optional[bool] = False
    recruitment: Optional[bool] = False
    onboarding: Optional[bool] = False
    time_tracking: Optional[bool] = False
    benefits: Optional[bool] = False
    reporting: Optional[bool] = False
    
    class Config:
        extra = "allow"  # Allow additional module flags


class PlanCreate(BaseModel):
    """Schema for creating a new plan"""
    name: str = Field(..., min_length=1, max_length=100, description="Plan name")
    slug: str = Field(..., min_length=1, max_length=50, description="URL-safe slug")
    description: Optional[str] = Field(None, description="Marketing description")
    
    # Pricing (in cents) - Monthly and Yearly for each region
    price_monthly_usd: int = Field(0, ge=0, description="Monthly price in USD cents")
    price_yearly_usd: int = Field(0, ge=0, description="Yearly price in USD cents")
    price_monthly_gbp: int = Field(0, ge=0, description="Monthly price in GBP cents")
    price_yearly_gbp: int = Field(0, ge=0, description="Yearly price in GBP cents")
    price_monthly_eur: int = Field(0, ge=0, description="Monthly price in EUR cents")
    price_yearly_eur: int = Field(0, ge=0, description="Yearly price in EUR cents")
    price_monthly_inr: int = Field(0, ge=0, description="Monthly price in INR paise")
    price_yearly_inr: int = Field(0, ge=0, description="Yearly price in INR paise")
    
    # Limits
    max_employees: int = Field(-1, description="Max employees (-1 = unlimited)")
    max_admin_users: int = Field(1, ge=1, description="Max admin users")
    
    # Features
    modules_json: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Feature flags")
    api_access: bool = Field(False, description="API access enabled")
    sso_enabled: bool = Field(False, description="SSO/SAML enabled")
    white_label: bool = Field(False, description="White label enabled")
    
    # Support & Trial
    support_tier: SupportTierEnum = Field(SupportTierEnum.community, description="Support tier")
    has_trial: bool = Field(True, description="Enable free trial for this plan")
    trial_days: int = Field(14, ge=0, le=90, description="Trial period in days (0-90)")
    
    # Regions
    regions_allowed: Optional[List[str]] = Field(default_factory=lambda: ["US"], description="Allowed regions")
    
    # Display
    sort_order: int = Field(0, description="Display order")
    
    @validator('slug')
    def validate_slug(cls, v):
        """Validate slug format"""
        if not re.match(r'^[a-z0-9]+(-[a-z0-9]+)*$', v):
            raise ValueError('Slug must be lowercase alphanumeric with hyphens only')
        return v
    
    class Config:
        schema_extra = {
            "example": {
                "name": "Growth",
                "slug": "growth",
                "description": "Perfect for growing teams",
                "price_monthly_usd": 9900,
                "price_yearly_usd": 99000,
                "price_monthly_gbp": 7900,
                "price_yearly_gbp": 79000,
                "price_monthly_eur": 8900,
                "price_yearly_eur": 89000,
                "price_monthly_inr": 79900,
                "price_yearly_inr": 799000,
                "max_employees": 100,
                "max_admin_users": 5,
                "modules_json": {"payroll": True, "ats": True, "performance": True},
                "api_access": True,
                "sso_enabled": False,
                "white_label": False,
                "support_tier": "email",
                "has_trial": True,
                "trial_days": 14,
                "regions_allowed": ["US", "UK", "EU", "IN"],
                "sort_order": 2
            }
        }


class PlanUpdate(BaseModel):
    """Schema for updating a plan (all fields optional)"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    slug: Optional[str] = Field(None, min_length=1, max_length=50)
    description: Optional[str] = None
    
    # Pricing (in cents) - Monthly and Yearly for each region
    price_monthly_usd: Optional[int] = Field(None, ge=0)
    price_yearly_usd: Optional[int] = Field(None, ge=0)
    price_monthly_gbp: Optional[int] = Field(None, ge=0)
    price_yearly_gbp: Optional[int] = Field(None, ge=0)
    price_monthly_eur: Optional[int] = Field(None, ge=0)
    price_yearly_eur: Optional[int] = Field(None, ge=0)
    price_monthly_inr: Optional[int] = Field(None, ge=0)
    price_yearly_inr: Optional[int] = Field(None, ge=0)
    
    # Limits
    max_employees: Optional[int] = None
    max_admin_users: Optional[int] = Field(None, ge=1)
    
    # Features
    modules_json: Optional[Dict[str, Any]] = None
    api_access: Optional[bool] = None
    sso_enabled: Optional[bool] = None
    white_label: Optional[bool] = None
    
    # Support & Trial
    support_tier: Optional[SupportTierEnum] = None
    has_trial: Optional[bool] = None
    trial_days: Optional[int] = Field(None, ge=0, le=90)
    
    # Regions
    regions_allowed: Optional[List[str]] = None
    
    # Status & Display
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None
    
    @validator('slug')
    def validate_slug(cls, v):
        """Validate slug format"""
        if v is not None and not re.match(r'^[a-z0-9]+(-[a-z0-9]+)*$', v):
            raise ValueError('Slug must be lowercase alphanumeric with hyphens only')
        return v


class PlanResponse(BaseModel):
    """Schema for plan response"""
    id: str
    name: str
    slug: str
    description: Optional[str]
    
    # Pricing - Monthly and Yearly for each region
    price_monthly_usd: int
    price_yearly_usd: int
    price_monthly_gbp: int
    price_yearly_gbp: int
    price_monthly_eur: int
    price_yearly_eur: int
    price_monthly_inr: int
    price_yearly_inr: int
    
    # Limits
    max_employees: int
    max_admin_users: int
    
    # Features
    modules_json: Dict[str, Any]
    api_access: bool
    sso_enabled: bool
    white_label: bool
    
    # Support & Trial
    support_tier: SupportTierEnum
    has_trial: bool
    trial_days: int
    
    # Regions
    regions_allowed: List[str]
    
    # Status & Display
    is_active: bool
    sort_order: int
    
    # Timestamps
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True
        schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "name": "Growth",
                "slug": "growth",
                "description": "Perfect for growing teams",
                "price_monthly_usd": 9900,
                "price_yearly_usd": 99000,
                "price_monthly_gbp": 7900,
                "price_yearly_gbp": 79000,
                "price_monthly_eur": 8900,
                "price_yearly_eur": 89000,
                "price_monthly_inr": 79900,
                "price_yearly_inr": 799000,
                "max_employees": 100,
                "max_admin_users": 5,
                "modules_json": {"payroll": True, "ats": True, "performance": True},
                "api_access": True,
                "sso_enabled": False,
                "white_label": False,
                "support_tier": "email",
                "has_trial": True,
                "trial_days": 14,
                "regions_allowed": ["US", "UK", "EU", "IN"],
                "is_active": True,
                "sort_order": 2,
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z"
            }
        }


class PlanListResponse(BaseModel):
    """Schema for paginated plan list response"""
    plans: List[PlanResponse]
    total: int
    page: int = 1
    per_page: int = 20
    
    class Config:
        schema_extra = {
            "example": {
                "plans": [],
                "total": 0,
                "page": 1,
                "per_page": 20
            }
        }
