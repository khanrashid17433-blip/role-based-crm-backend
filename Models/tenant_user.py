from beanie import Document
from pydantic import Field, EmailStr
from datetime import datetime
from typing import Optional, List, Any
from uuid import UUID, uuid4
import enum
from Models.enums import CompanySize, PrimaryRegion, BillingCycle


class TenantStatus(str, enum.Enum):
    """Tenant status enumeration"""
    trial = "trial"
    active = "active"
    suspended = "suspended"
    cancelled = "cancelled"
    churned = "churned"


class UserStatus(str, enum.Enum):
    """User status enumeration"""
    pending_verification = "pending_verification"
    active = "active"
    suspended = "suspended"
    deactivated = "deactivated"


class UserType(str, enum.Enum):
    """User type enumeration"""
    tenant_admin = "tenant_admin"
    admin_user = "admin_user"
    employee = "employee"
    platform_admin = "platform_admin"


class AuthProvider(str, enum.Enum):
    """Authentication provider enumeration"""
    local = "local"
    google = "google"
    microsoft = "microsoft"
    saml = "saml"
    oidc = "oidc"


class MfaType(str, enum.Enum):
    """MFA type enumeration"""
    totp = "totp"
    email_otp = "email_otp"
    sms_otp = "sms_otp"


class Tenant(Document):
    """Tenant model - Created on email verification"""
    
    # ID and timestamps
    id: UUID = Field(default_factory=uuid4, alias="_id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Basic Information
    name: str = Field(..., max_length=200)
    slug: str = Field(..., max_length=100, unique=True)
    subdomain: str = Field(..., max_length=100, unique=True)
    
    # Status & Plan
    status: TenantStatus = Field(default=TenantStatus.trial)
    plan_id: Optional[UUID] = None  # Reference to plans
    primary_region: PrimaryRegion
    primary_currency: str = Field(..., max_length=3)  # USD, GBP, INR
    
    # Company Details
    company_size: Optional[CompanySize] = None
    industry: Optional[str] = Field(None, max_length=100)
    
    # Trial & Billing
    trial_ends_at: Optional[datetime] = None
    billing_cycle: BillingCycle
    
    # Regional Settings
    fiscal_year_start: int = Field(default=1, ge=1, le=12)  # 1-12
    date_format: str = Field(default="MM/DD/YYYY", max_length=20)
    timezone: str = Field(default="America/New_York", max_length=50)
    
    # Branding
    logo_url: Optional[str] = None
    brand_color: Optional[str] = Field(None, max_length=7)  # Hex color
    
    # Onboarding
    onboarding_completed: bool = Field(default=False)
    onboarding_step: int = Field(default=1, ge=1, le=6)  # 1-6
    
    # Audit
    registration_id: Optional[UUID] = None  # Reference to tenant_registrations
    settings_json: dict = Field(default_factory=dict)
    
    # Soft Delete
    deleted_at: Optional[datetime] = None
    
    class Settings:
        name = "tenants"
        indexes = [
            "slug",
            "subdomain",
            "status",
        ]
    
    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v)
        }
    
    def __repr__(self):
        return f"<Tenant {self.name} ({self.slug})>"


class User(Document):
    """User model - Created on email verification"""
    
    # ID and timestamps
    id: UUID = Field(default_factory=uuid4, alias="_id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Tenant Relationship
    tenant_id: UUID
    
    # Email
    email: EmailStr = Field(..., unique=True)
    email_verified: bool = Field(default=False)
    email_verified_at: Optional[datetime] = None
    
    # Personal Information
    first_name: str = Field(..., max_length=100)
    last_name: str = Field(..., max_length=100)
    display_name: Optional[str] = Field(None, max_length=200)
    
    # Phone
    phone: Optional[str] = Field(None, max_length=20)
    phone_verified: bool = Field(default=False)
    
    # Profile
    avatar_url: Optional[str] = None
    
    # Authentication
    password_hash: Optional[str] = None  # Nullable for SSO users
    auth_provider: AuthProvider = Field(default=AuthProvider.local)
    auth_provider_id: Optional[str] = Field(None, max_length=255)  # External provider ID
    
    # Status
    status: UserStatus = Field(default=UserStatus.pending_verification)
    user_type: UserType = Field(default=UserType.tenant_admin)
    role: Optional[str] = Field(None, max_length=50)  # hr_admin, payroll_admin, recruiter, etc.
    role_id: Optional[Any] = None  # Reference to roles collection for RBAC
    
    # Login Tracking
    last_login_at: Optional[datetime] = None
    last_login_ip: Optional[str] = None  # Store as string instead of INET
    failed_login_count: int = Field(default=0)
    locked_until: Optional[datetime] = None
    
    # MFA
    mfa_enabled: bool = Field(default=False)
    mfa_type: Optional[MfaType] = None
    mfa_secret: Optional[str] = None  # Encrypted TOTP secret
    mfa_backup_codes: List[str] = Field(default_factory=list)  # 10 hashed backup codes
    
    # Preferences
    timezone: Optional[str] = Field(None, max_length=50)  # User-level override
    locale: Optional[str] = Field(None, max_length=20)  # e.g., en-US, en-GB
    
    # Security
    force_password_change: bool = Field(default=False)
    
    # Soft Delete
    deleted_at: Optional[datetime] = None
    created_by: Optional[UUID] = None  # Reference to users (NULL for self-registration)
    
    class Settings:
        name = "users"
        indexes = [
            "email",
            "tenant_id",
            "status",
            "user_type",
        ]
    
    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v)
        }
    
    def __repr__(self):
        return f"<User {self.email} ({self.user_type.value})>"


# Alias for backward compatibility
TenantUser = User
