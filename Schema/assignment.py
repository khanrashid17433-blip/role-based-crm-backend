from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from uuid import UUID
from Models.assignment import ResourceType

class BulkAssignRequest(BaseModel):
    resource_type: ResourceType
    resource_ids: List[UUID]
    to_user_id: UUID
    reason: Optional[str] = None

class ReassignRequest(BaseModel):
    resource_type: ResourceType
    resource_id: UUID
    to_user_id: UUID
    reason: str = Field(..., description="Reason for reassignment is required")

class ClientTeamUpdateRequest(BaseModel):
    client_tenant_id: UUID
    primary_csm_id: UUID
    secondary_csm_id: Optional[UUID] = None
    onboarding_specialist_id: Optional[UUID] = None
    technical_support_lead_id: Optional[UUID] = None
    account_executive_id: UUID
    notification_preferences: Dict[str, List[str]] = Field(default_factory=dict)

class AssignmentRuleCreateRequest(BaseModel):
    name: str
    resource_type: ResourceType = ResourceType.lead
    conditions: Dict[str, Any]
    assign_to_team_lead_id: Optional[UUID] = None
    assign_to_user_ids: List[UUID] = Field(default_factory=list)
