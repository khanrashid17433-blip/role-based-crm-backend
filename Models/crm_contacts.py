from beanie import Document
from pydantic import Field, EmailStr
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID, uuid4

class CrmCompany(Document):
    id: UUID = Field(default_factory=uuid4, alias="_id")
    tenant_id: UUID
    name: str = Field(..., max_length=200)
    domain: Optional[str] = Field(None, max_length=200)
    industry: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=50)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "crm_companies"
        indexes = ["tenant_id", "name"]

class CrmContact(Document):
    id: UUID = Field(default_factory=uuid4, alias="_id")
    tenant_id: UUID
    
    # Lead Relationship
    lead_id: Optional[UUID] = None  # FK to crm_leads
    
    first_name: str = Field(..., max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    full_name: Optional[str] = Field(None, max_length=200)
    email: EmailStr
    phone: Optional[str] = Field(None, max_length=20)
    alternate_phone: Optional[str] = Field(None, max_length=20)
    
    company_id: Optional[UUID] = None
    company_name: Optional[str] = Field(None, max_length=200)  # Store company name directly
    industry: Optional[str] = Field(None, max_length=100)
    company_size: Optional[str] = Field(None, max_length=50)
    owner_id: Optional[UUID] = None
    
    job_title: Optional[str] = Field(None, max_length=100)
    department: Optional[str] = Field(None, max_length=100)
    website: Optional[str] = Field(None, max_length=200)
    linkedin_url: Optional[str] = Field(None, max_length=200)
    
    address: Optional[str] = Field(None, max_length=200)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    region: Optional[str] = Field(None, max_length=100)
    country: Optional[str] = Field(None, max_length=100)
    postal_code: Optional[str] = Field(None, max_length=20)
    
    status: Optional[str] = Field(default="active")  # active, inactive, converted
    lead_status: Optional[str] = Field(default="new")
    lifecycle_stage: Optional[str] = Field(default="contact")
    source: Optional[str] = Field(default="manual")  # From lead source
    lead_source: Optional[str] = Field(default="manual")
    priority: Optional[str] = Field(None, max_length=20)  # hot, warm, cold
    
    tags: List[str] = Field(default_factory=list)
    avatar: Optional[str] = None
    notes: Optional[str] = None
    notes_list: List[Dict[str, Any]] = Field(default_factory=list)  # Copy from lead
    documents: List[Dict[str, Any]] = Field(default_factory=list)  # Copy from lead
    
    is_archived: bool = Field(default=False)
    is_deleted: bool = Field(default=False)
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: Optional[UUID] = None
    updated_by: Optional[UUID] = None
    last_activity_at: Optional[datetime] = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "crm_contacts"
        indexes = ["tenant_id", "email", "phone", "owner_id", "is_archived", "is_deleted"]

class CrmTimeline(Document):
    id: UUID = Field(default_factory=uuid4, alias="_id")
    contact_id: UUID
    activity_type: str  # e.g., contact_created, note_added, task_created, meeting_scheduled, call_completed, email_sent, etc.
    description: str
    performed_by: Optional[UUID] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "crm_timeline"
        indexes = ["contact_id", "activity_type", "created_at"]

class CrmContactNote(Document):
    id: UUID = Field(default_factory=uuid4, alias="_id")
    contact_id: UUID
    tenant_id: UUID
    lead_id: Optional[UUID] = None
    body: str
    created_by: UUID
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "crm_contact_notes"
        indexes = ["contact_id", "tenant_id", "lead_id"]

class CrmContactCall(Document):
    id: UUID = Field(default_factory=uuid4, alias="_id")
    contact_id: UUID
    tenant_id: UUID
    lead_id: Optional[UUID] = None
    subject: str = Field(..., max_length=200)
    notes: Optional[str] = None
    outcome: Optional[str] = Field(default="connected")  # busy, connected, no_answer, left_voicemail
    duration_seconds: Optional[int] = Field(default=0)
    created_by: UUID
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "crm_contact_calls"
        indexes = ["contact_id", "tenant_id", "lead_id"]

class CrmContactMeeting(Document):
    id: UUID = Field(default_factory=uuid4, alias="_id")
    contact_id: UUID
    tenant_id: UUID
    lead_id: Optional[UUID] = None
    title: str = Field(..., max_length=200)
    description: Optional[str] = None
    start_time: datetime
    end_time: datetime
    outcome: Optional[str] = Field(default="scheduled")  # scheduled, completed, no_show, cancelled
    created_by: UUID
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "crm_contact_meetings"
        indexes = ["contact_id", "tenant_id", "lead_id"]

class CrmContactEmail(Document):
    id: UUID = Field(default_factory=uuid4, alias="_id")
    contact_id: UUID
    tenant_id: UUID
    lead_id: Optional[UUID] = None
    subject: str = Field(..., max_length=200)
    body: str
    direction: str = Field(default="outbound")  # inbound, outbound
    created_by: UUID
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "crm_contact_emails"
        indexes = ["contact_id", "tenant_id", "lead_id"]
