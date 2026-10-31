from fastapi import APIRouter, Depends, HTTPException, status
from typing import Dict, Any, List
from uuid import UUID
import logging

from Schema.assignment import BulkAssignRequest, ReassignRequest, ClientTeamUpdateRequest, AssignmentRuleCreateRequest
from Services.assignment_service import AssignmentService
from Utility.auth_helpers import get_current_user, verify_tenant_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/assignments", tags=["Team Assignment & Workload"])

@router.post("/bulk", summary="Bulk Assign Leads/Tasks")
async def bulk_assign(data: BulkAssignRequest, current_user = Depends(get_current_user)):
    try:
        tenant_id = UUID(current_user.get('tid'))
        assigned_by = UUID(current_user.get('sub'))
        count = await AssignmentService.process_bulk_assignment(tenant_id, assigned_by, data)
        return {"message": f"Successfully assigned {count} records"}
    except Exception as e:
        logger.error(f"Failed to bulk assign: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.post("/reassign", summary="Reassign Single Resource")
async def reassign_resource(data: ReassignRequest, current_user = Depends(get_current_user)):
    try:
        tenant_id = UUID(current_user.get('tid'))
        assigned_by = UUID(current_user.get('sub'))
        history = await AssignmentService.process_reassignment(tenant_id, assigned_by, data)
        return {"message": "Resource reassigned", "history_id": str(history.id)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/client-team", summary="Configure Client Account Team (Post-Sale)")
async def update_client_team(data: ClientTeamUpdateRequest, current_user = Depends(get_current_user)):
    try:
        tenant_id = UUID(current_user.get('tid'))
        team = await AssignmentService.update_client_team(tenant_id, data)
        return {"message": "Client team updated", "team_id": str(team.id)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/rules", summary="Create Auto-Assignment Rule")
async def create_rule(data: AssignmentRuleCreateRequest, current_user = Depends(verify_tenant_admin)):
    try:
        tenant_id = UUID(current_user.get('tid'))
        rule = await AssignmentService.create_auto_assignment_rule(tenant_id, data)
        return {"message": "Rule created", "rule_id": str(rule.id)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/workload", summary="Get Team Workload Snapshots")
async def get_team_workload(user_ids: str, current_user = Depends(get_current_user)):
    """Pass user_ids as a comma-separated list"""
    try:
        tenant_id = UUID(current_user.get('tid'))
        uuid_list = [UUID(uid.strip()) for uid in user_ids.split(",")]
        snapshots = await AssignmentService.get_team_workload_snapshots(tenant_id, uuid_list)
        return snapshots
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format in user_ids")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
