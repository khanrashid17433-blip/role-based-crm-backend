from beanie import Document, before_event, Update, Delete
from pydantic import Field
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4
import enum


class EventSeverity(str, enum.Enum):
    """Security event severity levels"""
    info = "info"
    warning = "warning"
    critical = "critical"


class SecurityEvent(Document):
    """
    Security events audit log (append-only, never update/delete)
    
    Tracks critical security events like:
    - account_locked
    - password_changed
    - mfa_enabled/disabled
    - sso_config_changed
    - admin_role_granted
    - session_family_revoked
    - suspicious_login
    - data_export
    - bulk_delete
    
    IMPORTANT: This collection is APPEND-ONLY. Updates and deletes are blocked.
    """
    
    # ID and timestamps
    id: UUID = Field(default_factory=uuid4, alias="_id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Context
    tenant_id: Optional[UUID] = None
    user_id: Optional[UUID] = None
    
    # Event Details
    event_type: str = Field(..., max_length=100)
    severity: EventSeverity = Field(default=EventSeverity.info)
    
    # Actor (who performed the action - may differ from user_id for admin actions)
    actor_id: Optional[UUID] = None
    
    # Request Context
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    
    # Event Metadata
    metadata_json: Optional[dict] = None  # {old_value, new_value, reason, affected_records}
    
    class Settings:
        name = "security_events"
        indexes = [
            "tenant_id",
            "user_id",
            "event_type",
            "severity",
        ]
    
    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v)
        }
    
    def __repr__(self):
        return f"<SecurityEvent {self.event_type} ({self.severity.value})>"


# Prevent updates and deletes on SecurityEvent (append-only enforcement)
@before_event(Update)
async def prevent_security_event_update(self):
    """Prevent any updates to security_events collection"""
    raise ValueError("security_events collection is append-only. Updates are not allowed.")


@before_event(Delete)
async def prevent_security_event_delete(self):
    """Prevent any deletes from security_events collection"""
    raise ValueError("security_events collection is append-only. Deletes are not allowed.")
