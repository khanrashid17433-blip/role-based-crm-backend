from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Optional
from uuid import UUID

class TicketCommentCreate(BaseModel):
    text: str

class TicketCommentResponse(BaseModel):
    sender: str
    role: str
    text: str
    time: datetime
    avatar_letter: str
    user_id: UUID

    model_config = {
        "from_attributes": True
    }

class TicketActivityResponse(BaseModel):
    action: str
    time: datetime
    user_name: str

    model_config = {
        "from_attributes": True
    }

class TicketCreate(BaseModel):
    employee_name: str
    department: str
    issue_type: str
    priority: str
    description: str
    attachments: Optional[List[dict]] = Field(default_factory=list)

class TicketUpdateStatus(BaseModel):
    status: str

class TicketAssign(BaseModel):
    assigned_to: str
    assigned_to_id: UUID
    assigned_role: str

class BulkStatusUpdate(BaseModel):
    ticket_ids: List[UUID]
    status: str

class BulkAssignUpdate(BaseModel):
    ticket_ids: List[UUID]
    assigned_to: str
    assigned_to_id: UUID
    assigned_role: str

class BulkDelete(BaseModel):
    ticket_ids: List[UUID]

class TicketResponse(BaseModel):
    id: UUID
    ticket_seq_id: str
    tenant_id: UUID
    employee_name: str
    employee_id: UUID
    department: str
    issue_type: str
    priority: str
    status: str
    description: str
    assigned_to: str
    assigned_to_id: Optional[UUID] = None
    assigned_role: Optional[str] = None
    created_at: datetime
    comments: List[TicketCommentResponse] = Field(default_factory=list)
    activity: List[TicketActivityResponse] = Field(default_factory=list)
    attachments: List[dict] = Field(default_factory=list)

    model_config = {
        "from_attributes": True
    }

class TicketsListResponse(BaseModel):
    tickets: List[TicketResponse]

    model_config = {
        "from_attributes": True
    }

