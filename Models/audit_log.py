from beanie import Document
from pydantic import Field
from uuid import UUID, uuid4
from datetime import datetime

class SettingsAuditLog(Document):
    id: UUID = Field(default_factory=uuid4, alias="_id")
    user_email: str
    user_name: str
    action: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "settings_audit_logs"
        indexes = ["timestamp"]
