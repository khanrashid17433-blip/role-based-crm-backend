from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Optional
from uuid import UUID

class AnnouncementCreate(BaseModel):
    title: str = Field(..., max_length=200)
    content: str
    type: str = Field(default="general") # important, general, hr_updates

class AnnouncementResponse(BaseModel):
    id: str
    title: str
    content: str
    type: str
    author_id: str
    author_name: str
    created_at: datetime
    is_read: bool = False

class AnnouncementStats(BaseModel):
    total: int
    unread: int
    important: int
    this_week: int

class AnnouncementsListResponse(BaseModel):
    stats: AnnouncementStats
    announcements: List[AnnouncementResponse]
