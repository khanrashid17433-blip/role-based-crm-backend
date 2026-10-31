from pydantic import BaseModel, Field, EmailStr
from typing import Optional, Dict, Any, List
from enum import Enum
from datetime import datetime


class TenantStatusEnum(str, Enum):
    """Tenant status options"""
    trial = "trial"
    active = "active"
    suspended = "suspended"
    cancelled = "cancelled"
    churned = "churned"


class UserStatusEnum(str, Enum):
    """User status options"""
    pending_verification = "pending_verification"
    active = "active"
    suspended = "suspended"
    deactivated = "deactivated"


class UserTypeEnum(str, Enum):
    """User type options"""
    tenant_admin = "tenant_admin"
    admin_user = "admin_user"
    employee = "employee"
    platform_admin = "platform_admin"


class AuthProviderEnum(str, Enum):
    """Auth provider options"""
    local = "local"
    google = "google"
    microsoft = "microsoft"
    saml = "saml"
    oidc = "oidc"


class MfaTypeEnum(str, Enum):
    """MFA type options"""
    totp = "totp"
    email_otp = "email_otp"
    sms_otp = "sms_otp"


class TenantResponse(BaseModel):
    """Tenant response schema"""
    id: str
    name: str
    slug: str
    subdomain: str
    status: TenantStatusEnum
    plan_id: Optional[str]
    primary_region: str
    primary_currency: str
    company_size: Optional[str]
    industry: Optional[str]
    trial_ends_at: Optional[datetime]
    billing_cycle: str
    fiscal_year_start: int
    date_format: str
    timezone: str
    logo_url: Optional[str]
    brand_color: Optional[str]
    onboarding_completed: bool
    onboarding_step: int
    settings_json: Optional[Dict[str, Any]]
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class UserResponse(BaseModel):
    """User response schema (public - no sensitive data)"""
    id: str
    tenant_id: str
    email: EmailStr
    email_verified: bool
    first_name: str
    last_name: str
    display_name: Optional[str]
    phone: Optional[str]
    phone_verified: bool
    avatar_url: Optional[str]
    auth_provider: AuthProviderEnum
    status: UserStatusEnum
    user_type: UserTypeEnum
    role: Optional[str] = Field(None, description="User role (hr_admin, payroll_admin, recruiter, finance_viewer, it_admin, etc.)")
    last_login_at: Optional[datetime]
    mfa_enabled: bool
    mfa_type: Optional[MfaTypeEnum]
    timezone: Optional[str]
    locale: Optional[str]
    force_password_change: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class VerificationSuccessResponse(BaseModel):
    """Email verification success response with tokens"""
    message: str
    access_token: str
    refresh_token: str
    redirect_to: str = "/onboarding/step/1"
    user: UserResponse
    tenant: TenantResponse
    
    class Config:
        schema_extra = {
            "example": {
                "message": "Email verified successfully!",
                "access_token": "eyJhbGciOiJIUzI1NiIs...",
                "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
                "redirect_to": "/onboarding/step/1",
                "user": {
                    "id": "uuid",
                    "email": "john@company.com",
                    "first_name": "John",
                    "last_name": "Doe",
                    "user_type": "tenant_admin"
                },
                "tenant": {
                    "id": "uuid",
                    "name": "Acme Corporation",
                    "slug": "acme-corp"
                }
            }
        }


class LoginRequest(BaseModel):
    """Login request schema"""
    email: EmailStr = Field(..., description="User email")
    password: str = Field(..., description="User password")
    
    class Config:
        schema_extra = {
            "example": {
                "email": "john@company.com",
                "password": "SecureP@ss123!"
            }
        }


class LoginResponse(BaseModel):
    """Login response schema"""
    access_token: str
    refresh_token: str
    user: UserResponse
    tenant: TenantResponse
    
    class Config:
        schema_extra = {
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIs...",
                "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
                "user": {},
                "tenant": {}
            }
        }


class TokenRefreshRequest(BaseModel):
    """Token refresh request"""
    refresh_token: str = Field(..., description="Refresh token")


class TokenRefreshResponse(BaseModel):
    """Token refresh response"""
    access_token: str
    refresh_token: str
