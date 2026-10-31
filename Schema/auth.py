from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List
from datetime import datetime


class LoginRequest(BaseModel):
    """Login request with rememberMe support"""
    email: EmailStr = Field(..., description="User email")
    password: str = Field(..., description="User password")
    remember_me: bool = Field(False, description="Remember device for 30 days")
    device_fingerprint: Optional[str] = Field(None, description="SHA-256 hash of device fingerprint")
    
    class Config:
        json_schema_extra = {
            "example": {
                "email": "john@company.com",
                "password": "SecureP@ss123!",
                "remember_me": True,
                "device_fingerprint": "abc123..."
            }
        }


class MFARequiredResponse(BaseModel):
    """Response when MFA is required"""
    mfa_required: bool = True
    mfa_token: str = Field(..., description="Temporary MFA session token (10 min expiry)")
    mfa_type: str = Field(..., description="MFA type: totp, email_otp, sms_otp")
    masked_email: Optional[str] = Field(None, description="Masked email for OTP delivery")
    message: str = "MFA verification required"


class MFAVerifyRequest(BaseModel):
    """MFA verification request"""
    mfa_token: str = Field(..., description="MFA session token from login response")
    code: str = Field(..., description="6-digit OTP or 8-char backup code")
    remember_device: bool = Field(False, description="Trust this device for 30 days")
    device_fingerprint: Optional[str] = Field(None, description="SHA-256 hash of device fingerprint")
    
    class Config:
        json_schema_extra = {
            "example": {
                "mfa_token": "eyJhbGciOiJIUzI1NiIs...",
                "code": "123456",
                "remember_device": True,
                "device_fingerprint": "abc123..."
            }
        }


class LoginSuccessResponse(BaseModel):
    """Successful login response"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 86400  # 24 hours
    user: dict
    tenant: dict


class ForgotPasswordRequest(BaseModel):
    """Forgot password request"""
    email: EmailStr = Field(..., description="User email")


class ResetPasswordRequest(BaseModel):
    """Reset password request"""
    token: str = Field(..., description="Password reset token from email")
    new_password: str = Field(..., min_length=12, description="New password (min 12 chars)")
    confirm_password: str = Field(..., description="Confirm new password")


class MagicLinkRequest(BaseModel):
    """Magic link login request"""
    email: EmailStr = Field(..., description="User email")


class RefreshTokenRequest(BaseModel):
    """Refresh token request"""
    refresh_token: str = Field(..., description="Refresh token")


class SSOConfigCheckRequest(BaseModel):
    """SSO configuration check request"""
    email: EmailStr = Field(..., description="User email to check for SSO")


class SSOConfigResponse(BaseModel):
    """SSO configuration response"""
    has_sso: bool
    sso_type: Optional[str] = None
    entity_id: Optional[str] = None
    sso_url: Optional[str] = None
    message: Optional[str] = None


class TrustedDeviceResponse(BaseModel):
    """Trusted device response"""
    id: str
    device_name: str
    ip_address: str
    trusted_at: datetime
    last_used_at: Optional[datetime]
    expires_at: datetime


class LoginEventResponse(BaseModel):
    """Login event response"""
    id: str
    event_type: str
    ip_address: str
    location: Optional[dict]
    created_at: datetime
    flagged: bool
    risk_score: int
