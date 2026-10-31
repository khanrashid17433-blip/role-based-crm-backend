from beanie import Document
from pydantic import Field, BaseModel
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from uuid import UUID, uuid4
import enum

# ==========================================
# ENUMS
# ==========================================

class ProjectType(str, enum.Enum):
    client_implementation = "client_implementation"
    internal = "internal"
    product_feature = "product_feature"
    support = "support"
    sales_pursuit = "sales_pursuit"

class ProjectStatus(str, enum.Enum):
    not_started = "not_started"
    planning = "planning"
    in_progress = "in_progress"
    on_hold = "on_hold"
    completed = "completed"
    cancelled = "cancelled"

class Priority(str, enum.Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"

class TaskStatus(str, enum.Enum):
    to_do = "to_do"
    in_progress = "in_progress"
    blocked = "blocked"
    in_review = "in_review"
    done = "done"
    cancelled = "cancelled"

class ResourceType(str, enum.Enum):
    lead = "lead"
    deal = "deal"
    client = "client"
    employee = "employee"
    onboarding = "onboarding"

# ==========================================
# PROJECT MODELS
# ==========================================

class Project(Document):
    id: UUID = Field(default_factory=uuid4, alias="_id")
    tenant_id: UUID
    type: ProjectType
    name: str = Field(..., max_length=200)
    
    client: Optional[str] = None
    client_logo: Optional[str] = None
    client_color: Optional[str] = None
    
    client_tenant_id: Optional[UUID] = None
    lead_id: Optional[UUID] = None
    deal_id: Optional[UUID] = None
    
    department: Optional[str] = None
    status: ProjectStatus = Field(default=ProjectStatus.not_started)
    priority: Priority = Field(default=Priority.medium)
    
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    actual_end_date: Optional[datetime] = None
    
    budget: Optional[float] = None
    currency: Optional[str] = None
    progress: Optional[int] = Field(default=None)
    
    description_html: Optional[str] = None
    tags_json: List[str] = Field(default_factory=list)
    
    created_by: UUID
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "projects"
        indexes = ["tenant_id", "status", "lead_id"]

class ProjectMember(Document):
    id: UUID = Field(default_factory=uuid4, alias="_id")
    project_id: UUID
    user_id: UUID
    role: str = Field(default="member") # lead, member, observer, stakeholder
    added_by: UUID
    added_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "project_members"
        indexes = ["project_id", "user_id"]

class ProjectMilestone(Document):
    id: UUID = Field(default_factory=uuid4, alias="_id")
    project_id: UUID
    title: str = Field(..., max_length=200)
    due_date: Optional[date] = None
    status: str = Field(default="pending") # pending, completed
    completed_at: Optional[datetime] = None
    description: Optional[str] = None
    owner_id: Optional[UUID] = None
    
    class Settings:
        name = "project_milestones"
        indexes = ["project_id"]

# ==========================================
# TASK MODELS
# ==========================================

class TaskComment(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    text: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

class Task(Document):
    id: UUID = Field(default_factory=uuid4, alias="_id")
    tenant_id: UUID
    project_id: Optional[UUID] = None
    parent_task_id: Optional[UUID] = None
    
    title: str = Field(..., max_length=255)
    description_html: Optional[str] = None
    
    related_type: Optional[ResourceType] = None
    related_id: Optional[UUID] = None
    
    assigned_to: UUID
    created_by: UUID
    
    priority: Priority = Field(default=Priority.medium)
    status: TaskStatus = Field(default=TaskStatus.to_do)
    
    due_at: Optional[datetime] = None
    reminder_at: Optional[datetime] = None
    estimated_hours: Optional[float] = None
    
    tags_json: List[str] = Field(default_factory=list)
    
    comments: List[TaskComment] = Field(default_factory=list)
    attachments: List[dict] = Field(default_factory=list)
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "tasks"
        indexes = ["tenant_id", "project_id", "assigned_to", "status"]

class TaskWatcher(Document):
    id: UUID = Field(default_factory=uuid4, alias="_id")
    task_id: UUID
    user_id: UUID
    added_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "task_watchers"

class TaskSubtask(Document):
    id: UUID = Field(default_factory=uuid4, alias="_id")
    task_id: UUID
    title: str = Field(..., max_length=255)
    completed: bool = False
    completed_by: Optional[UUID] = None
    completed_at: Optional[datetime] = None
    sort_order: int = 0
    
    class Settings:
        name = "task_subtasks"

class TaskAttachment(Document):
    id: UUID = Field(default_factory=uuid4, alias="_id")
    task_id: UUID
    file_url: str
    file_name: str
    file_size: int
    uploaded_by: UUID
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "task_attachments"

class TaskTimeEntry(Document):
    id: UUID = Field(default_factory=uuid4, alias="_id")
    task_id: UUID
    user_id: UUID
    started_at: datetime
    ended_at: Optional[datetime] = None
    duration_mins: Optional[int] = None
    note: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "task_time_entries"
        
class TaskLabel(Document):
    id: UUID = Field(default_factory=uuid4, alias="_id")
    tenant_id: UUID
    name: str
    color_hex: str
    created_by: UUID
    
    class Settings:
        name = "task_labels"

class TaskLabelAssignment(Document):
    id: UUID = Field(default_factory=uuid4, alias="_id")
    task_id: UUID
    label_id: UUID
    
    class Settings:
        name = "task_label_assignments"
