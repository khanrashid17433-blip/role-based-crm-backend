from beanie import Document
from pydantic import Field, BaseModel
from datetime import datetime
from typing import Optional, List
from uuid import UUID, uuid4

class TicketComment(BaseModel):
    sender: str
    role: str
    text: str
    time: datetime = Field(default_factory=datetime.utcnow)
    avatar_letter: str
    user_id: UUID

class TicketActivity(BaseModel):
    action: str
    time: datetime = Field(default_factory=datetime.utcnow)
    user_name: str

class Ticket(Document):
    id: UUID = Field(default_factory=uuid4, alias="_id")
    ticket_seq_id: str  # e.g., TKT-2024-00125
    tenant_id: UUID
    employee_name: str
    employee_id: UUID
    department: str
    issue_type: str
    priority: str  # High, Medium, Low
    status: str = "Open"  # Open, In Progress, Closed
    description: str
    assigned_to: str = "Unassigned"
    assigned_to_id: Optional[UUID] = None
    assigned_role: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    comments: List[TicketComment] = Field(default_factory=list)
    activity: List[TicketActivity] = Field(default_factory=list)
    attachments: List[dict] = Field(default_factory=list)  # e.g., [{"name": "file.png", "size": "456 KB"}]

    class Settings:
        name = "tickets"
        indexes = [
            "tenant_id",
            "status",
            "priority",
            "employee_id",
            "ticket_seq_id"
        ]

    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v)
        }
