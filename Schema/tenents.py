from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List
from datetime import datetime
from uuid import UUID
from Models.enums import PrimaryRegion, BillingCycle, CompanySize, RegistrationStatus
from Models.tenant_user import TenantStatus, UserStatus, UserType, AuthProvider


class TenantResponse(BaseModel):
    """Single tenant response schema"""
    id: UUID
    name: str
    slug: str
    subdomain: str
    status: TenantStatus
    primary_region: PrimaryRegion
    primary_currency: str
    company_size: Optional[CompanySize] = None
    industry: Optional[str] = None
    billing_cycle: BillingCycle
    trial_ends_at: Optional[datetime] = None
    onboarding_completed: bool
    onboarding_step: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True
        use_enum_values = True


class TenantListResponse(BaseModel):
    """Response schema for listing tenants"""
    tenants: List[TenantResponse]
    total: int
    page: int
    limit: int
    has_more: bool


class TenantDetailResponse(TenantResponse):
    """Detailed tenant response with admin user info"""
    admin_email: Optional[EmailStr] = None
    admin_name: Optional[str] = None
    admin_phone: Optional[str] = None


class LeadResponse(BaseModel):
    """Single lead (unverified registration) response schema"""
    id: UUID
    email: EmailStr
    first_name: str
    last_name: str
    phone: Optional[str] = None
    company_name: Optional[str] = None  # Can be None for step 1 only registrations
    company_size: Optional[CompanySize] = None  # Can be None for step 1 only registrations
    industry: Optional[str] = None
    primary_region: Optional[PrimaryRegion] = None  # Can be None for step 1 only registrations
    plan_slug: Optional[str] = None  # Can be None for step 1 only registrations
    billing_cycle: Optional[BillingCycle] = None  # Can be None for step 1 only registrations
    promo_code: Optional[str] = None
    registration_status: RegistrationStatus
    verification_attempts: int
    expires_at: datetime
    converted_at: Optional[datetime] = None
    converted_tenant_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True
        use_enum_values = True


class LeadListResponse(BaseModel):
    """Response schema for listing leads"""
    leads: List[LeadResponse]
    total: int
    page: int
    limit: int
    has_more: bool


class SuperAdminSettingsResponse(BaseModel):
    """Super admin settings response schema"""
    platform_name: str = "B2B Platform"
    total_tenants: int
    active_tenants: int
    trial_tenants: int
    suspended_tenants: int
    total_leads: int
    pending_leads: int
    system_health: str = "healthy"
    last_updated: datetime
    
    class Config:
        from_attributes = True


class UserResponse(BaseModel):
    """Single user response schema for super admin"""
    id: UUID
    tenant_id: UUID
    tenant_name: Optional[str] = None
    email: EmailStr
    first_name: str
    last_name: str
    display_name: str
    phone: Optional[str] = None
    status: UserStatus
    user_type: UserType
    auth_provider: AuthProvider
    email_verified: bool
    email_verified_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None
    last_login_ip: Optional[str] = None
    failed_login_count: int
    mfa_enabled: bool
    role: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True
        use_enum_values = True


class UserListResponse(BaseModel):
    """Response schema for listing users"""
    users: List[UserResponse]
    total: int
    page: int
    limit: int
    has_more: bool
