from beanie import Document
from pydantic import Field
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID, uuid4
import enum


class DealCallType(str, enum.Enum):
    inbound = "inbound"
    outbound = "outbound"
    internal = "internal"


class DealMeetingStatus(str, enum.Enum):
    scheduled = "scheduled"
    ongoing = "ongoing"
    completed = "completed"
    cancelled = "cancelled"


class DealTaskStatus(str, enum.Enum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"


class DealTaskPriority(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    urgent = "urgent"


class CrmDealNote(Document):
    id: UUID = Field(default_factory=uuid4, alias="_id")
    deal_id: UUID
    tenant_id: UUID
    note: str
    is_pinned: bool = False
    created_by: UUID
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "crm_deal_notes"
        indexes = ["deal_id", "tenant_id", "is_pinned"]


class CrmDealCall(Document):
    id: UUID = Field(default_factory=uuid4, alias="_id")
    deal_id: UUID
    tenant_id: UUID
    call_type: DealCallType = DealCallType.outbound
    duration: Optional[int] = None  # seconds
    outcome: Optional[str] = None
    notes: Optional[str] = None
    created_by: UUID
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "crm_deal_calls"
        indexes = ["deal_id", "tenant_id"]


class CrmDealMeeting(Document):
    id: UUID = Field(default_factory=uuid4, alias="_id")
    deal_id: UUID
    tenant_id: UUID
    title: str
    agenda: Optional[str] = None
    meeting_link: Optional[str] = None
    start_time: datetime
    end_time: Optional[datetime] = None
    status: DealMeetingStatus = DealMeetingStatus.scheduled
    outcome: Optional[str] = None
    created_by: UUID
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "crm_deal_meetings"
        indexes = ["deal_id", "tenant_id", "status"]


class CrmDealTask(Document):
    id: UUID = Field(default_factory=uuid4, alias="_id")
    deal_id: UUID
    tenant_id: UUID
    title: str
    description: Optional[str] = None
    priority: DealTaskPriority = DealTaskPriority.medium
    status: DealTaskStatus = DealTaskStatus.pending
    due_date: Optional[datetime] = None
    assigned_to: Optional[UUID] = None
    created_by: UUID
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None

    class Settings:
        name = "crm_deal_tasks"
        indexes = ["deal_id", "tenant_id", "status", "assigned_to"]


class CrmDealDocument(Document):
    id: UUID = Field(default_factory=uuid4, alias="_id")
    deal_id: UUID
    tenant_id: UUID
    file_name: str
    file_url: Optional[str] = None
    file_size: Optional[str] = None
    file_type: Optional[str] = None
    uploaded_by: UUID
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "crm_deal_documents"
        indexes = ["deal_id", "tenant_id"]


class CrmDealActivityFeed(Document):
    """Unified activity feed for deals - tracks all actions"""
    id: UUID = Field(default_factory=uuid4, alias="_id")
    deal_id: UUID
    tenant_id: UUID
    activity_type: str  # note, call, meeting, task, email, document, proposal, stage_change, system
    title: str
    description: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_by: UUID
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "crm_deal_activity_feed"
        indexes = ["deal_id", "tenant_id", "activity_type"]