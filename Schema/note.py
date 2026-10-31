from pydantic import BaseModel, Field
from typing import Optional, List
from uuid import UUID

class NoteCreateRequest(BaseModel):
    resource_type: str = Field(..., max_length=50) # lead, opportunity, client, project, task, employee
    resource_id: UUID
    parent_note_id: Optional[UUID] = None
    
    body_html: str
    body_plain: str
    
    note_type: str = "general"
    visibility: str = "internal"
    is_pinned: bool = False
    
    mentions: List[UUID] = Field(default_factory=list)

class NoteUpdateRequest(BaseModel):
    body_html: Optional[str] = None
    body_plain: Optional[str] = None
    note_type: Optional[str] = None
    visibility: Optional[str] = None
    is_pinned: Optional[bool] = None
    
class ReactionRequest(BaseModel):
    emoji: str = Field(..., max_length=10)
