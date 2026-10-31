from beanie import Document
from pydantic import Field, EmailStr
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID, uuid4
from Models.enums import CompanySize, PrimaryRegion, BillingCycle, RegistrationStatus


class TenantRegistration(Document):
    """Tenant Registration model - Pre-verification staging collection"""
    
    # ID and timestamps
    id: UUID = Field(default_factory=uuid4, alias="_id")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Personal Information
    email: EmailStr = Field(..., unique=True)
    first_name: str = Field(..., max_length=100)
    last_name: str = Field(..., max_length=100)
    phone: str = Field(..., max_length=20)  # E.164 format - Required
    
    # Authentication
    password_hash: str  # Argon2id hash
    
    # Company Information (nullable for Step 1 / lead creation)
    company_name: Optional[str] = Field(None, max_length=200)
    company_size: Optional[CompanySize] = None
    industry: Optional[str] = Field(None, max_length=100)
    primary_region: Optional[PrimaryRegion] = None
    
    # Plan & Billing (nullable for Step 1 / lead creation)
    plan_slug: Optional[str] = Field(None, max_length=50)
    billing_cycle: Optional[BillingCycle] = None
    promo_code: Optional[str] = Field(None, max_length=50)
    
    # Legal Compliance
    terms_accepted: bool = Field(default=False)
    terms_accepted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Status & Verification
    registration_status: RegistrationStatus = Field(default=RegistrationStatus.pending_verification)
    verification_attempts: int = Field(default=0)
    
    # Timestamps
    expires_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc) + timedelta(hours=48))
    converted_at: Optional[datetime] = None
    converted_tenant_id: Optional[UUID] = None
    
    class Settings:
        name = "tenant_registrations"
        indexes = [
            "email",
            "registration_status",
        ]
    
    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v)
        }
    
    def __repr__(self):
        return f"<TenantRegistration {self.email} - {self.registration_status.value}>"
