from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, date
from uuid import UUID

# ── Task Enums ──

class TaskType(str):
    call = "call"
    email = "email"
    meeting = "meeting"
    follow_up = "follow_up"
    reminder = "reminder"
    demo = "demo"
    proposal = "proposal"
    document_review = "document_review"
    internal = "internal"

class TaskPriority(str):
    high = "high"
    medium = "medium"
    low = "low"
    urgent = "urgent"

class TaskStatus(str):
    not_started = "not_started"
    in_progress = "in_progress"
    waiting = "waiting"
    completed = "completed"
    cancelled = "cancelled"

# ── Request Schemas ──

class TaskCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    type: str = Field(default="task", max_length=50)
    priority: str = Field(default="medium")
    status: str = Field(default="not_started")
    due_date: Optional[datetime] = None
    due_time: Optional[str] = None
    reminder_time: Optional[str] = None
    reminder_type: Optional[str] = None
    repeat: Optional[str] = None
    owner_id: Optional[str] = None
    assigned_to: Optional[str] = None
    lead_id: Optional[str] = None
    contact_id: Optional[str] = None
    deal_id: Optional[str] = None
    company_id: Optional[str] = None
    attachments: Optional[List[Dict[str, Any]]] = None
    notes: Optional[str] = None
    checklist: Optional[List[Dict[str, Any]]] = None
    estimated_time: Optional[int] = None

class TaskUpdateRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    type: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    due_date: Optional[datetime] = None
    due_time: Optional[str] = None
    reminder_time: Optional[str] = None
    reminder_type: Optional[str] = None
    repeat: Optional[str] = None
    owner_id: Optional[str] = None
    assigned_to: Optional[str] = None
    lead_id: Optional[str] = None
    contact_id: Optional[str] = None
    deal_id: Optional[str] = None
    company_id: Optional[str] = None
    notes: Optional[str] = None
    estimated_time: Optional[int] = None
    checklist: Optional[List[Dict[str, Any]]] = None

class TaskCommentRequest(BaseModel):
    text: str = Field(..., min_length=1)
    mentions: Optional[List[str]] = None
    parent_id: Optional[str] = None

class TaskChecklistItemRequest(BaseModel):
    text: str = Field(..., min_length=1)
    completed: bool = False

class TaskAttachmentRequest(BaseModel):
    file_name: str
    file_url: str
    file_size: Optional[str] = None
    file_type: Optional[str] = None

# ── Task Filter Params ──

class TaskFilterParams(BaseModel):
    status: Optional[str] = None
    priority: Optional[str] = None
    type: Optional[str] = None
    owner_id: Optional[str] = None
    assigned_to: Optional[str] = None
    lead_id: Optional[str] = None
    contact_id: Optional[str] = None
    deal_id: Optional[str] = None
    company_id: Optional[str] = None
    due_date_from: Optional[datetime] = None
    due_date_to: Optional[datetime] = None
    search: Optional[str] = None
    page: int = 1
    limit: int = 50
    sort_by: str = "created_at"
    sort_order: str = "desc"