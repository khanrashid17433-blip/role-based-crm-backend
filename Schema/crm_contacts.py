from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID

class CompanyCreate(BaseModel):
    name: str = Field(..., max_length=200)
    domain: Optional[str] = Field(None, max_length=200)
    industry: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=50)

class CrmContactCreate(BaseModel):
    first_name: str = Field(..., max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    email: EmailStr
    phone: Optional[str] = Field(None, max_length=20)
    alternate_phone: Optional[str] = Field(None, max_length=20)
    
    company_id: Optional[UUID] = None
    company_name: Optional[str] = Field(None, max_length=200) # For auto-creation of company
    owner_id: Optional[UUID] = None
    
    job_title: Optional[str] = Field(None, max_length=100)
    department: Optional[str] = Field(None, max_length=100)
    website: Optional[str] = Field(None, max_length=200)
    
    address: Optional[str] = Field(None, max_length=200)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    country: Optional[str] = Field(None, max_length=100)
    postal_code: Optional[str] = Field(None, max_length=20)
    
    lead_status: Optional[str] = Field(default="new")
    lifecycle_stage: Optional[str] = Field(default="lead")
    lead_source: Optional[str] = Field(default="manual")
    
    tags: List[str] = Field(default_factory=list)
    notes: Optional[str] = None

class CrmContactUpdate(BaseModel):
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=20)
    alternate_phone: Optional[str] = Field(None, max_length=20)
    
    company_id: Optional[UUID] = None
    owner_id: Optional[UUID] = None
    
    job_title: Optional[str] = Field(None, max_length=100)
    department: Optional[str] = Field(None, max_length=100)
    website: Optional[str] = Field(None, max_length=200)
    
    address: Optional[str] = Field(None, max_length=200)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    country: Optional[str] = Field(None, max_length=100)
    postal_code: Optional[str] = Field(None, max_length=20)
    
    lead_status: Optional[str] = None
    lifecycle_stage: Optional[str] = None
    lead_source: Optional[str] = None
    
    tags: Optional[List[str]] = None
    notes: Optional[str] = None

class ContactSearchRequest(BaseModel):
    search_query: Optional[str] = None
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=10, ge=1)
    sort_by: str = "created_at"
    sort_order: str = "desc"  # asc or desc

class ContactFilterRequest(BaseModel):
    lifecycle_stage: Optional[str] = None
    lead_status: Optional[str] = None
    owner_id: Optional[UUID] = None
    is_archived: Optional[bool] = None
    tags: Optional[List[str]] = None
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=10, ge=1)
    sort_by: str = "created_at"
    sort_order: str = "desc"

class BulkUpdateRequest(BaseModel):
    ids: List[UUID]
    updates: Dict[str, Any]

class MergeRequest(BaseModel):
    primary_id: UUID
    secondary_id: UUID

class CrmContactNoteCreate(BaseModel):
    body: str

class CrmContactCallCreate(BaseModel):
    subject: str = Field(..., max_length=200)
    notes: Optional[str] = None
    outcome: str = "connected"
    duration_seconds: int = 0

class CrmContactMeetingCreate(BaseModel):
    title: str = Field(..., max_length=200)
    description: Optional[str] = None
    start_time: datetime
    end_time: datetime
    outcome: str = "scheduled"

class CrmContactEmailCreate(BaseModel):
    subject: str = Field(..., max_length=200)
    body: str
    direction: str = "outbound"
