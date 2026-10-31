from beanie import Document
from pydantic import Field
from uuid import UUID, uuid4
from datetime import datetime
from typing import Optional

class PlatformSettings(Document):
    id: UUID = Field(default_factory=uuid4, alias="_id")
    
    # General
    platform_name: str = "Bhoomi Techzone HRMS"
    support_email: str = "support@bhoomitechzone.com"
    maintenance_mode: bool = False
    registration_enabled: bool = True
    
    # Security
    session_timeout: int = 60 # minutes
    require_2fa: bool = False
    min_password_length: int = 8
    password_expiry_days: int = 90
    jwt_expiry_hours: int = 24
    
    # Email
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    email_sender: str = "noreply@bhoomitechzone.com"
    
    # Notifications
    email_notifications: bool = True
    in_app_notifications: bool = True
    announcement_alerts: bool = True
    notify_new_tenant: bool = True
    notify_payment_failed: bool = True
    notify_system_errors: bool = True
    notify_security_alerts: bool = True
    
    # API
    api_rate_limit: int = 1000
    master_api_key: str = "sk-1234567890abcdef"
    
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "platform_settings"
