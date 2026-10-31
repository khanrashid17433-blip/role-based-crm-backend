from beanie import Document
from pydantic import Field
from datetime import datetime, date
from typing import Optional, List, Any, Dict
from uuid import UUID, uuid4
import enum

class ResourceType(str, enum.Enum):
    lead = "lead"
    deal = "deal"
    client = "client"
    project = "project"
    task = "task"

class AssignmentHistory(Document):
    id: UUID = Field(default_factory=uuid4, alias="_id")
    tenant_id: UUID
    resource_type: ResourceType
    resource_id: UUID
    from_user_id: Optional[UUID] = None
    to_user_id: UUID
    assigned_by: UUID
    reason: Optional[str] = None
    assigned_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "assignment_history"
        indexes = ["tenant_id", "resource_type", "resource_id", "to_user_id"]

class WorkloadSnapshot(Document):
    id: UUID = Field(default_factory=uuid4, alias="_id")
    tenant_id: UUID
    user_id: UUID
    snapshot_date: date
    open_leads: int = 0
    open_deals: int = 0
    active_clients: int = 0
    open_tasks: int = 0
    
    class Settings:
        name = "workload_snapshots"
        indexes = ["tenant_id", "user_id", "snapshot_date"]

class ClientAccountTeam(Document):
    id: UUID = Field(default_factory=uuid4, alias="_id")
    tenant_id: UUID
    client_tenant_id: UUID
    
    primary_csm_id: UUID
    secondary_csm_id: Optional[UUID] = None
    onboarding_specialist_id: Optional[UUID] = None
    technical_support_lead_id: Optional[UUID] = None
    account_executive_id: UUID
    
    notification_preferences: Dict[str, List[str]] = Field(default_factory=dict) # e.g. {"support_tickets": ["primary_csm_id", "technical_support_lead_id"]}
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "client_account_teams"
        indexes = ["tenant_id", "client_tenant_id"]

class AutoAssignmentRule(Document):
    id: UUID = Field(default_factory=uuid4, alias="_id")
    tenant_id: UUID
    name: str
    resource_type: ResourceType = ResourceType.lead
    
    # Simple rule representation
    conditions: Dict[str, Any] = Field(default_factory=dict) # e.g., {"source": "meta_ads", "region": "US"}
    assign_to_team_lead_id: Optional[UUID] = None
    assign_to_user_ids: List[UUID] = Field(default_factory=list) # For round-robin
    last_assigned_index: int = 0 # Track round robin state
    
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "auto_assignment_rules"
