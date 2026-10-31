from beanie import Document
from pydantic import Field
from datetime import datetime
from typing import Optional, List
from uuid import UUID, uuid4
import enum


class LoginEventType(str, enum.Enum):
    """Login event type enumeration"""
    login_success = "login_success"
    login_failed = "login_failed"
    mfa_success = "mfa_success"
    mfa_failed = "mfa_failed"
    sso_login = "sso_login"
    magic_link_login = "magic_link_login"
    logout = "logout"
    password_reset = "password_reset"
    account_locked = "account_locked"
    suspicious_activity = "suspicious_activity"


class RevokeReason(str, enum.Enum):
    """Refresh token revoke reason"""
    logout = "logout"
    rotation = "rotation"
    family_compromised = "family_compromised"
    admin_revoke = "admin_revoke"
    password_change = "password_change"


class SSOType(str, enum.Enum):
    """SSO type enumeration"""
    saml = "saml"
    oidc = "oidc"
    google_workspace = "google_workspace"
    microsoft_entra = "microsoft_entra"


class TrustedDevice(Document):
    """Trusted devices for MFA bypass"""
    
    # ID and timestamps
    id: UUID = Field(default_factory=uuid4, alias="_id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    user_id: UUID
    device_fingerprint: str = Field(..., max_length=64)  # SHA-256 hash
    device_name: str = Field(..., max_length=200)  # e.g., "Chrome on macOS"
    ip_address: str  # Store as string instead of INET
    trusted_at: datetime
    expires_at: datetime  # 30 days default
    last_used_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    
    class Settings:
        name = "trusted_devices"
        indexes = [
            "user_id",
            "device_fingerprint",
        ]
    
    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v)
        }
    
    def __repr__(self):
        return f"<TrustedDevice {self.device_name} for user {self.user_id}>"


class RefreshToken(Document):
    """Refresh tokens with rotation and family tracking"""
    
    # ID and timestamps
    id: UUID = Field(default_factory=uuid4, alias="_id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    user_id: UUID
    tenant_id: UUID
    token_hash: str = Field(..., max_length=128, unique=True)  # SHA-256
    family_id: UUID  # Groups rotated tokens
    parent_token_id: Optional[UUID] = None
    device_fingerprint: Optional[str] = Field(None, max_length=64)
    ip_address: str  # Store as string instead of INET
    user_agent: Optional[str] = None
    expires_at: datetime
    revoked_at: Optional[datetime] = None
    revoke_reason: Optional[RevokeReason] = None
    last_used_at: Optional[datetime] = None
    
    class Settings:
        name = "refresh_tokens"
        indexes = [
            "user_id",
            "tenant_id",
            "token_hash",
            "family_id",
        ]
    
    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v)
        }
    
    def __repr__(self):
        return f"<RefreshToken for user {self.user_id} (family {self.family_id})>"


class LoginEvent(Document):
    """Login events and audit log"""
    
    # ID and timestamps
    id: UUID = Field(default_factory=uuid4, alias="_id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    user_id: UUID
    tenant_id: UUID
    event_type: LoginEventType
    ip_address: str  # Store as string instead of INET
    user_agent: Optional[str] = None
    device_fingerprint: Optional[str] = Field(None, max_length=64)
    location_json: Optional[dict] = None  # {city, country, lat, lng}
    failure_reason: Optional[str] = Field(None, max_length=100)
    risk_score: int = Field(default=0, ge=0, le=100)  # 0-100
    flagged: bool = Field(default=False)
    
    class Settings:
        name = "login_events"
        indexes = [
            "user_id",
            "tenant_id",
            "event_type",
        ]
    
    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v)
        }
    
    def __repr__(self):
        return f"<LoginEvent {self.event_type.value} for user {self.user_id}>"


class PasswordHistory(Document):
    """Password history for preventing reuse"""
    
    # ID and timestamps
    id: UUID = Field(default_factory=uuid4, alias="_id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    user_id: UUID
    password_hash: str  # Argon2id hash
    
    class Settings:
        name = "password_history"
        indexes = [
            "user_id",
        ]
    
    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v)
        }
    
    def __repr__(self):
        return f"<PasswordHistory for user {self.user_id}>"


class SSOConfiguration(Document):
    """SSO configuration for SAML/OIDC"""
    
    # ID and timestamps
    id: UUID = Field(default_factory=uuid4, alias="_id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    tenant_id: UUID
    domain: str = Field(..., max_length=255, unique=True)  # e.g., "acmecorp.com"
    sso_type: SSOType
    is_active: bool = Field(default=True)
    
    # SAML fields
    saml_entity_id: Optional[str] = None
    saml_sso_url: Optional[str] = None
    saml_certificate: Optional[str] = None  # Encrypted at rest
    
    # OIDC fields
    oidc_client_id: Optional[str] = None
    oidc_client_secret: Optional[str] = None  # Encrypted
    oidc_discovery_url: Optional[str] = None
    
    # Attribute mapping
    attribute_mapping_json: Optional[dict] = None
    
    # JIT provisioning
    jit_provisioning: bool = Field(default=False)
    default_role_id: Optional[UUID] = None
    
    class Settings:
        name = "sso_configurations"
        indexes = [
            "tenant_id",
            "domain",
        ]
    
    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v)
        }
    
    def __repr__(self):
        return f"<SSOConfiguration {self.domain} ({self.sso_type.value})>"


class MagicLinkToken(Document):
    """Magic link tokens for passwordless login"""
    
    # ID and timestamps
    id: UUID = Field(default_factory=uuid4, alias="_id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    user_id: UUID
    token_hash: str = Field(..., max_length=128, unique=True)  # SHA-256
    email: str = Field(..., max_length=255)
    ip_address: str  # Store as string instead of INET
    expires_at: datetime  # 15 minutes
    used_at: Optional[datetime] = None
    
    class Settings:
        name = "magic_link_tokens"
        indexes = [
            "user_id",
            "token_hash",
        ]
    
    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v)
        }
    
    def __repr__(self):
        return f"<MagicLinkToken for user {self.user_id}>"
