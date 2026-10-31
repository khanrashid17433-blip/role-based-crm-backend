from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime
from uuid import UUID

class PlatformSettingsBase(BaseModel):
    # General
    platform_name: Optional[str] = None
    support_email: Optional[str] = None
    maintenance_mode: Optional[bool] = None
    registration_enabled: Optional[bool] = None
    
    # Security
    session_timeout: Optional[int] = None
    require_2fa: Optional[bool] = None
    min_password_length: Optional[int] = None
    password_expiry_days: Optional[int] = None
    jwt_expiry_hours: Optional[int] = None
    
    # Email
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    email_sender: Optional[str] = None
    
    # Notifications
    email_notifications: Optional[bool] = None
    in_app_notifications: Optional[bool] = None
    announcement_alerts: Optional[bool] = None
    notify_new_tenant: Optional[bool] = None
    notify_payment_failed: Optional[bool] = None
    notify_system_errors: Optional[bool] = None
    notify_security_alerts: Optional[bool] = None
    
    # API
    api_rate_limit: Optional[int] = None
    master_api_key: Optional[str] = None

class PlatformSettingsUpdate(PlatformSettingsBase):
    pass

class PlatformSettingsResponse(PlatformSettingsBase):
    id: UUID
    updated_at: datetime
    
    class Config:
        from_attributes = True

class SettingsAuditLogResponse(BaseModel):
    id: UUID
    user_email: str
    user_name: str
    action: str
    timestamp: datetime
    
    class Config:
        from_attributes = True
