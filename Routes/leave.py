from fastapi import APIRouter, HTTPException, status, Depends
from typing import List
from datetime import datetime
from beanie import PydanticObjectId
from Utility.auth_helpers import verify_tenant_admin
from uuid import UUID
import logging

logger = logging.getLogger(__name__)

# Import your Beanie Model
from Models.leave import LeavePolicy

# Import schema (if separate)
from Schema.leave import (
    LeavePolicyCreate,
    LeavePolicyUpdate
)

router = APIRouter(
    prefix="/api/leave-policy",
    tags=["Leave Policy"]
)

# ✅ CREATE Leave Policy
from Models.leave import LeavePolicy  # ✅ CHECK THIS IMPORT

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_leave_policy(
    data: LeavePolicyCreate,
    current_user = Depends(verify_tenant_admin)
):
    try:
        tenant_id = UUID(current_user.get("tid"))

        policy = LeavePolicy(
            **data.dict(),
            tenant_id=tenant_id
        )

        await policy.insert()

        return {
            "message": "Leave Policy Created Successfully",
            "data": policy
        }

    except Exception as e:
        logger.error(f"Create policy failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")

   
# ✅ GET ALL Leave Policies
@router.get("/")
async def get_all_policies():
    policies = await LeavePolicy.find(
        LeavePolicy.tenant_id != None
    ).to_list()
    return policies


# ✅ GET SINGLE Leave Policy
@router.get("/{policy_id}", response_model=LeavePolicy)
async def get_policy(policy_id: PydanticObjectId):
    policy = await LeavePolicy.get(policy_id)

    if not policy:
        raise HTTPException(
            status_code=404,
            detail="Leave Policy not found"
        )
    
    return policy


# ✅ UPDATE Leave Policy
@router.put("/{policy_id}")
async def update_policy(policy_id: str, data: LeavePolicyUpdate):
    try:
        obj_id = PydanticObjectId(policy_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid policy ID format")

    policy = await LeavePolicy.get(obj_id)

    if not policy:
        raise HTTPException(status_code=404, detail="Leave Policy not found")

    update_data = data.dict(exclude_unset=True)

    for key, value in update_data.items():
        setattr(policy, key, value)

    policy.updated_at = datetime.utcnow()

    await policy.save()
    return policy


# ✅ DELETE Leave Policy
@router.delete("/{policy_id}")
async def delete_policy(policy_id: str):
    try:
        obj_id = PydanticObjectId(policy_id)

        policy = await LeavePolicy.get(obj_id)

        if not policy:
            raise HTTPException(status_code=404, detail="Leave Policy not found")

        await policy.delete()

        return {"message": "Leave Policy deleted successfully"}

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid ID format: {str(e)}")