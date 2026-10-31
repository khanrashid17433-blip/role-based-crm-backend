from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import logging
from uuid import UUID
from beanie.operators import In

from Models.assignment import AssignmentHistory, WorkloadSnapshot, ClientAccountTeam, AutoAssignmentRule, ResourceType
from Schema.assignment import BulkAssignRequest, ReassignRequest, ClientTeamUpdateRequest, AssignmentRuleCreateRequest

logger = logging.getLogger(__name__)

class AssignmentService:

    @staticmethod
    async def log_assignment(tenant_id: UUID, resource_type: ResourceType, resource_id: UUID, to_user_id: UUID, assigned_by: UUID, from_user_id: Optional[UUID] = None, reason: Optional[str] = None):
        """Creates an immutable log of an assignment action."""
        history = AssignmentHistory(
            tenant_id=tenant_id,
            resource_type=resource_type,
            resource_id=resource_id,
            from_user_id=from_user_id,
            to_user_id=to_user_id,
            assigned_by=assigned_by,
            reason=reason
        )
        await history.insert()
        return history

    @staticmethod
    async def process_bulk_assignment(tenant_id: UUID, assigned_by: UUID, data: BulkAssignRequest) -> int:
        """Assign multiple leads/tasks to a single user (usually by a Dept Head)."""
        count = 0
        for resource_id in data.resource_ids:
            # Here we would typically update the underlying resource (Lead, Task, etc.)
            # e.g., await Lead.find_one(...).update({"$set": {"assigned_to": data.to_user_id}})
            
            await AssignmentService.log_assignment(
                tenant_id=tenant_id,
                resource_type=data.resource_type,
                resource_id=resource_id,
                to_user_id=data.to_user_id,
                assigned_by=assigned_by,
                reason=data.reason or "Bulk assignment"
            )
            count += 1
        return count

    @staticmethod
    async def process_reassignment(tenant_id: UUID, assigned_by: UUID, data: ReassignRequest) -> AssignmentHistory:
        """Reassign a single resource from one rep to another."""
        # Typically find the old owner first
        # old_owner_id = await get_resource_owner(data.resource_type, data.resource_id)
        old_owner_id = None # Placeholder for actual lookup
        
        # Update the underlying resource
        # e.g., await Resource.update(...)
        
        return await AssignmentService.log_assignment(
            tenant_id=tenant_id,
            resource_type=data.resource_type,
            resource_id=data.resource_id,
            from_user_id=old_owner_id,
            to_user_id=data.to_user_id,
            assigned_by=assigned_by,
            reason=data.reason
        )

    @staticmethod
    async def update_client_team(tenant_id: UUID, data: ClientTeamUpdateRequest) -> ClientAccountTeam:
        """Setup or update the post-sale client account team."""
        team = await ClientAccountTeam.find_one(
            ClientAccountTeam.tenant_id == tenant_id,
            ClientAccountTeam.client_tenant_id == data.client_tenant_id
        )
        
        if team:
            team.primary_csm_id = data.primary_csm_id
            team.secondary_csm_id = data.secondary_csm_id
            team.onboarding_specialist_id = data.onboarding_specialist_id
            team.technical_support_lead_id = data.technical_support_lead_id
            team.account_executive_id = data.account_executive_id
            team.notification_preferences = data.notification_preferences
            team.updated_at = datetime.utcnow()
            await team.save()
        else:
            team = ClientAccountTeam(
                tenant_id=tenant_id,
                client_tenant_id=data.client_tenant_id,
                primary_csm_id=data.primary_csm_id,
                secondary_csm_id=data.secondary_csm_id,
                onboarding_specialist_id=data.onboarding_specialist_id,
                technical_support_lead_id=data.technical_support_lead_id,
                account_executive_id=data.account_executive_id,
                notification_preferences=data.notification_preferences
            )
            await team.insert()
            
        return team

    @staticmethod
    async def create_auto_assignment_rule(tenant_id: UUID, data: AssignmentRuleCreateRequest) -> AutoAssignmentRule:
        """Admin configures a territory or round-robin rule."""
        rule = AutoAssignmentRule(
            tenant_id=tenant_id,
            name=data.name,
            resource_type=data.resource_type,
            conditions=data.conditions,
            assign_to_team_lead_id=data.assign_to_team_lead_id,
            assign_to_user_ids=data.assign_to_user_ids
        )
        await rule.insert()
        return rule

    @staticmethod
    async def get_team_workload_snapshots(tenant_id: UUID, user_ids: List[UUID]) -> List[WorkloadSnapshot]:
        """Fetch workload snapshots for a list of team members (for the Dept Head / Team Lead view)."""
        # Usually we would just get the most recent snapshot for the given users
        return await WorkloadSnapshot.find(
            WorkloadSnapshot.tenant_id == tenant_id,
            In(WorkloadSnapshot.user_id, user_ids)
        ).sort("-snapshot_date").to_list()
