from beanie import Document
from pydantic import Field
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

class Note(Document):
    id: UUID = Field(default_factory=uuid4, alias="_id")
    tenant_id: UUID
    resource_type: str = Field(..., max_length=50) # lead, opportunity, client, project, task, employee
    resource_id: UUID
    parent_note_id: Optional[UUID] = None # For threading (max 3 levels enforced in service)
    
    author_id: UUID
    body_html: str
    body_plain: str
    
    note_type: str = Field(default="general") # general, important, client_communication, internal_only
    visibility: str = Field(default="internal") # internal, client_visible
    
    is_pinned: bool = False
    is_deleted: bool = False
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "notes"
        indexes = ["tenant_id", "resource_type", "resource_id", "parent_note_id"]

class NoteMention(Document):
    id: UUID = Field(default_factory=uuid4, alias="_id")
    note_id: UUID
    mentioned_user_id: UUID
    notified_at: Optional[datetime] = None
    
    class Settings:
        name = "note_mentions"
        indexes = ["note_id", "mentioned_user_id"]

class NoteAttachment(Document):
    id: UUID = Field(default_factory=uuid4, alias="_id")
    note_id: UUID
    file_url: str
    file_name: str
    file_size: int
    uploaded_by: UUID
    
    class Settings:
        name = "note_attachments"
        indexes = ["note_id"]

class NoteReaction(Document):
    id: UUID = Field(default_factory=uuid4, alias="_id")
    note_id: UUID
    user_id: UUID
    emoji: str = Field(..., max_length=10)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "note_reactions"
        indexes = ["note_id"]

class NoteEdit(Document):
    id: UUID = Field(default_factory=uuid4, alias="_id")
    note_id: UUID
    previous_html: str
    edited_by: UUID
    edited_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "note_edits"
        indexes = ["note_id"]
