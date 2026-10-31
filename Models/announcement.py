from beanie import Document
from pydantic import Field
from datetime import datetime
from typing import Optional
from typing import Optional
from uuid import UUID, uuid4

class CompanyAnnouncement(Document):
    id: UUID = Field(default_factory=uuid4, alias="_id")
    tenant_id: UUID
    title: str = Field(..., max_length=200)
    content: str
    type: str = Field(default="general") # important, general, hr_updates
    author_id: UUID
    author_name: str
    note_id: Optional[UUID] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "company_announcements"
        indexes = ["tenant_id", "type", "created_at"]

class CompanyAnnouncementReadStatus(Document):
    id: UUID = Field(default_factory=uuid4, alias="_id")
    announcement_id: UUID
    employee_id: UUID
    read_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "company_announcement_read_status"
        indexes = ["announcement_id", "employee_id"]
