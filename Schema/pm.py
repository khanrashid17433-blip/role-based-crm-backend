from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, List
from datetime import date, datetime
from uuid import UUID
from Models.pm import ProjectType, ProjectStatus, Priority, TaskStatus, ResourceType

# --- PROJECT SCHEMAS ---

class ProjectCreateRequest(BaseModel):
    name: str = Field(..., max_length=200)
    type: ProjectType = ProjectType.internal
    client_tenant_id: Optional[UUID] = None
    department: Optional[str] = None
    priority: Priority = Priority.medium
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    budget: Optional[float] = None
    currency: Optional[str] = None
    progress: Optional[int] = Field(default=None, ge=0, le=100)
    description_html: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    lead_id: Optional[UUID] = None
    team_members: List[UUID] = Field(default_factory=list)

    @field_validator('type', mode='before')
    @classmethod
    def empty_str_to_default_type(cls, v):
        if v == '' or v is None:
            return ProjectType.internal
        return v

    @field_validator('priority', mode='before')
    @classmethod
    def empty_str_to_default_priority(cls, v):
        if v == '' or v is None:
            return Priority.medium
        return v

class ProjectUpdateRequest(BaseModel):
    name: Optional[str] = None
    type: Optional[ProjectType] = None
    client: Optional[str] = None
    department: Optional[str] = None
    status: Optional[ProjectStatus] = None
    priority: Optional[Priority] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    actual_end_date: Optional[datetime] = None
    budget: Optional[float] = None
    progress: Optional[int] = Field(default=None, ge=0, le=100)
    description_html: Optional[str] = None
    tags: Optional[List[str]] = None
    lead_id: Optional[UUID] = None
    team_members: Optional[List[UUID]] = None

    @field_validator('type', 'status', 'priority', 'lead_id', mode='before')
    @classmethod
    def empty_str_to_none_fields(cls, v):
        if v == '' or v is None:
            return None
        return v

    @field_validator('team_members', mode='before')
    @classmethod
    def filter_empty_team_members(cls, v):
        if v is None:
            return None
        # Remove empty strings and None values from the list
        return [m for m in v if m and str(m).strip() != '']

class MilestoneCreateRequest(BaseModel):
    title: str = Field(..., max_length=200)
    due_date: date
    description: Optional[str] = None
    owner_id: Optional[UUID] = None

# --- TASK SCHEMAS ---

class TaskCreateRequest(BaseModel):
    title: str = Field(..., max_length=255)
    description_html: Optional[str] = None
    project_id: Optional[UUID] = None
    parent_task_id: Optional[UUID] = None
    
    related_type: Optional[ResourceType] = None
    related_id: Optional[UUID] = None
    
    assigned_to: UUID
    watchers: List[UUID] = Field(default_factory=list)
    
    priority: Priority = Priority.medium
    status: TaskStatus = TaskStatus.to_do
    
    due_at: datetime
    reminder_at: Optional[datetime] = None
    estimated_hours: Optional[float] = None
    tags: List[str] = Field(default_factory=list)

    @field_validator('priority', mode='before')
    @classmethod
    def empty_str_to_default_priority(cls, v):
        if v == '' or v is None:
            return Priority.medium
        return v

    @field_validator('status', mode='before')
    @classmethod
    def empty_str_to_default_status(cls, v):
        if v == '' or v is None:
            return TaskStatus.to_do
        return v

class TaskUpdateRequest(BaseModel):
    status: Optional[TaskStatus] = None
    assigned_to: Optional[UUID] = None
    priority: Optional[Priority] = None

    @field_validator('status', 'priority', mode='before')
    @classmethod
    def empty_str_to_none_fields(cls, v):
        if v == '' or v is None:
            return None
        return v

class TaskSubtaskRequest(BaseModel):
    title: str
    sort_order: int = 0

class TaskTimeLogRequest(BaseModel):
    duration_mins: int
    note: Optional[str] = None
    started_at: datetime
    ended_at: datetime
