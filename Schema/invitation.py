from pydantic import BaseModel, Field, EmailStr
from typing import Optional, Dict, Any
from datetime import datetime
from uuid import UUID
from Models.enums import UserRole
from Models.tenant_user import UserType


class InvitationCreateSchema(BaseModel):
    """Schema for creating invitations"""
    email: EmailStr = Field(..., description="Employee email")
    first_name: str = Field(..., min_length=1, max_length=100, description="First name")
    last_name: str = Field(..., min_length=1, max_length=100, description="Last name")
    phone: Optional[str] = Field(None, description="Phone number")
    role: str = Field(..., description="Role: hr_admin, payroll_admin, recruiter, etc.")
    user_type: Optional[UserType] = Field(UserType.employee, description="User type")
    employee_id: Optional[UUID] = Field(None, description="Associated employee ID")
    personal_details: Optional[Dict[str, Any]] = Field(None, description="Pre-filled personal details")
    notification_prefs: Optional[Dict[str, Any]] = Field(None, description="Default notification preferences")


class InviteEmployeeRequest(BaseModel):
    """Request to invite an employee"""
    email: EmailStr = Field(..., description="Employee email")
    first_name: str = Field(..., min_length=1, max_length=100, description="First name")
    last_name: str = Field(..., min_length=1, max_length=100, description="Last name")
    phone: Optional[str] = Field(None, description="Phone number")
    role: str = Field(..., description="Role: hr_admin, payroll_admin, recruiter, etc.")
    employee_id: Optional[UUID] = Field(None, description="Associated employee ID")
    personal_details: Optional[Dict[str, Any]] = Field(None, description="Pre-filled personal details")
    notification_prefs: Optional[Dict[str, Any]] = Field(None, description="Default notification preferences")


class InviteEmployeeResponse(BaseModel):
    """Response after inviting an employee"""
    message: str
    invitation_id: str
    email: str
    expires_at: datetime


class ValidateInviteTokenRequest(BaseModel):
    """Request to validate invitation token"""
    token: str = Field(..., description="Invitation token from email link")


class ValidateInviteTokenResponse(BaseModel):
    """Response with pre-filled invitation data"""
    valid: bool
    email: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    company_name: Optional[str] = None
    role: Optional[str] = None
    personal_details: Optional[Dict[str, Any]] = None
    notification_prefs: Optional[Dict[str, Any]] = None
    message: Optional[str] = None


class AcceptInviteRequest(BaseModel):
    """Request to accept invitation and create account"""
    token: str = Field(..., description="Invitation token")
    password: str = Field(..., min_length=12, description="New password (min 12 chars)")
    confirm_password: str = Field(..., description="Confirm password")
    
    # Optional fields employee can update
    preferred_name: Optional[str] = Field(None, max_length=100, description="Preferred name")
    phone: Optional[str] = Field(None, description="Updated phone number")
    avatar_url: Optional[str] = Field(None, description="Profile photo URL")
    
    # Updated personal details
    personal_details: Optional[Dict[str, Any]] = Field(None, description="Updated personal details")
    
    # MFA setup (optional unless tenant requires it)
    setup_mfa: bool = Field(False, description="Set up MFA during onboarding")
    mfa_type: Optional[str] = Field(None, description="totp or email_otp")
    
    # Notification preferences
    notification_prefs: Optional[Dict[str, Any]] = Field(None, description="Notification preferences")


class AcceptInviteResponse(BaseModel):
    """Response after accepting invitation"""
    message: str
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 86400
    user: Dict[str, Any]
    tenant: Dict[str, Any]
    mfa_setup_required: bool = False
    mfa_qr_code: Optional[str] = None  # Base64 QR code for TOTP setup


class ResendInviteRequest(BaseModel):
    """Request to resend invitation email"""
    invitation_id: str = Field(..., description="Invitation ID")


class RevokeInviteRequest(BaseModel):
    """Request to revoke invitation"""
    invitation_id: str = Field(..., description="Invitation ID")
    reason: Optional[str] = Field(None, description="Reason for revocation")


class ListInvitationsResponse(BaseModel):
    """Response with list of invitations"""
    invitations: list
    total: int
    page: int
    page_size: int
