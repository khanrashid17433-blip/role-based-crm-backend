from beanie import Document
from pydantic import Field, EmailStr
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4


class TenantOnboarding(Document):
    """Tenant onboarding progress tracker"""
    
    # ID and timestamps
    id: UUID = Field(default_factory=uuid4, alias="_id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    tenant_id: UUID = Field(..., unique=True)
    
    # Progress tracking
    current_step: int = Field(default=0, description="Last completed step (0-6)")
    is_completed: bool = Field(default=False, description="Whether onboarding is fully completed")
    
    # Step data (dict for flexibility)
    step_1_company_profile: Optional[dict] = Field(None, description="Company profile data")
    step_2_entity: Optional[dict] = Field(None, description="First entity data")
    step_3_team_invites: Optional[dict] = Field(None, description="Team invitations data")
    step_4_payroll_config: Optional[dict] = Field(None, description="Payroll configuration")
    step_5_leave_policy: Optional[dict] = Field(None, description="Leave policy data")
    step_6_completion: Optional[dict] = Field(None, description="Completion checklist")
    
    class Settings:
        name = "tenant_onboarding"
        indexes = [
            "tenant_id",
        ]
    
    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v)
        }
    
    def __repr__(self):
        return f"<TenantOnboarding tenant_id={self.tenant_id} step={self.current_step}>"


class UserInvitation(Document):
    """User invitation model for inviting employees"""
    
    # ID and timestamps
    id: UUID = Field(default_factory=uuid4, alias="_id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Tenant & Inviter
    tenant_id: UUID
    invited_by: UUID
    
    # Invitee Information
    email: EmailStr
    first_name: str = Field(..., max_length=100)
    last_name: str = Field(..., max_length=100)
    phone: Optional[str] = Field(None, max_length=20)
    role: str = Field(..., max_length=50)  # hr_admin, payroll_admin, etc.
    user_type: str = Field(default="employee", max_length=50)  # employee, admin_user, etc.
    employee_id: Optional[UUID] = None
    
    # Invitation Token
    token_hash: str = Field(..., max_length=128, unique=True)  # SHA-256
    
    # Status
    status: str = Field(default="pending", max_length=20)  # pending, accepted, expired, revoked
    
    # Metadata
    personal_details_json: Optional[dict] = None  # Pre-filled data from HR
    notification_prefs_json: Optional[dict] = None  # Default notification preferences
    metadata_json: Optional[dict] = None  # Additional invite metadata
    
    # Expiry & Usage
    expires_at: datetime  # 7 days default
    accepted_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    revoked_by: Optional[UUID] = None
    revoke_reason: Optional[str] = Field(None, max_length=200)
    
    # Resend tracking
    resent_count: int = Field(default=0)
    last_resent_at: Optional[datetime] = None
    
    # IP Tracking
    invite_ip: Optional[str] = Field(None, max_length=50)
    accept_ip: Optional[str] = Field(None, max_length=50)
    
    # Created User
    created_user_id: Optional[UUID] = None
    
    class Settings:
        name = "user_invitations"
        indexes = [
            "tenant_id",
            "email",
            "token_hash",
            "employee_id",
            "status",
        ]
    
    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v)
        }
    
    def __repr__(self):
        return f"<UserInvitation {self.email} ({self.status})>"
