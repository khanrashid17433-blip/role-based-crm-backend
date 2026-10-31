from beanie import Document
from pydantic import Field
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID, uuid4

class CrmTask(Document):
    """HubSpot-style Task Management Model"""
    id: UUID = Field(default_factory=uuid4, alias="_id")
    tenant_id: UUID
    title: str = Field(..., max_length=200)
    description: Optional[str] = None
    type: str = Field(default="task", max_length=50)  # call, email, meeting, follow_up, reminder, demo, proposal, document_review, internal
    priority: str = Field(default="medium")  # high, medium, low, urgent
    status: str = Field(default="not_started")  # not_started, in_progress, waiting, completed, cancelled
    
    # Assignment
    owner_id: Optional[UUID] = None
    assigned_to: Optional[UUID] = None
    
    # Associations
    lead_id: Optional[UUID] = None
    contact_id: Optional[UUID] = None
    deal_id: Optional[UUID] = None
    company_id: Optional[UUID] = None
    
    # Dates & Times
    due_date: Optional[datetime] = None
    due_time: Optional[str] = None
    completed_at: Optional[datetime] = None
    
    # Reminder
    reminder_time: Optional[str] = None
    reminder_type: Optional[str] = None  # email, browser, in_app
    reminder_sent: bool = False
    
    # Repeat
    repeat: Optional[str] = None  # daily, weekly, monthly, yearly
    
    # Attachments, Comments, Checklist
    attachments: List[Dict[str, Any]] = Field(default_factory=list)
    comments: List[Dict[str, Any]] = Field(default_factory=list)
    checklist: List[Dict[str, Any]] = Field(default_factory=list)
    
    # Metadata
    notes: Optional[str] = None
    estimated_time: Optional[int] = None  # in minutes
    created_by: Optional[UUID] = None
    updated_by: Optional[UUID] = None
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    archived_at: Optional[datetime] = None
    
    class Settings:
        name = "crm_tasks"
        indexes = [
            "tenant_id",
            "status",
            "priority",
            "type",
            "owner_id",
            "assigned_to",
            "lead_id",
            "contact_id",
            "deal_id",
            "company_id",
            "due_date",
            "created_at"
        ]