from beanie import Document
from pydantic import Field
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4


class BaseModel(Document):
    """Base model with common fields for MongoDB"""
    
    id: UUID = Field(default_factory=uuid4, alias="_id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        # This will be overridden in child classes
        use_state_management = True
        validate_on_save = True
    
    class Config:
        # Allow population by field name and alias
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v)
        }
