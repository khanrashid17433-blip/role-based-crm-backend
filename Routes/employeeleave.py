from fastapi import APIRouter, Depends, HTTPException, status, Body
from typing import List, Optional
from uuid import UUID
from Utility.auth_helpers import get_current_user
# Import your Beanie Model
from Models.employeeleave import LeaveApplication
# Import schema (if separate)
from Schema.employeeleave import LeaveApplyRequest
from Utility.auth_helpers import get_current_user
from datetime import datetime
from bson import ObjectId
from beanie import PydanticObjectId
from pydantic import BaseModel


class LeaveActionRequest(BaseModel):
    status: str
    reason: Optional[str] = None


router = APIRouter(
    prefix="/api/employee-leave")
from datetime import datetime

@router.post("/apply")
async def apply_leave(
    data: LeaveApplyRequest,
    current_user=Depends(get_current_user)
):
    from Models.employee import Employee
    tenant_id = UUID(current_user.get("tid"))
    user_id = UUID(current_user.get("sub"))

    employee = await Employee.find_one(
        Employee.user_id == user_id,
        Employee.tenant_id == tenant_id
    )
    if not employee:
        raise HTTPException(status_code=404, detail="Employee profile not found")

    # ✅ Convert date → datetime
    start = datetime.combine(data.start_date, datetime.min.time())
    end = datetime.combine(data.end_date, datetime.min.time())

    # ✅ Calculate total days
    total_days = (end - start).days + 1

    # ✅ Create document (NO **data.dict())
    leave = LeaveApplication(
        start_date=start,
        end_date=end,
        leave_type=data.leave_type,
        reason=data.reason,
        total_days=total_days,

        tenant_id=tenant_id,
        employee_id=employee.id,
        employee_name=f"{employee.first_name} {employee.last_name}".strip() or current_user.get("email")
    )

    # ✅ Insert into MongoDB
    await leave.insert()

    return {
        "message": "Leave applied successfully",
        "data": leave
    }
@router.get("/my-leaves")
async def get_my_leaves(
    current_user = Depends(get_current_user)
):
    from Models.employee import Employee
    tenant_id = UUID(current_user["tid"])
    user_id = UUID(current_user["sub"])

    employee = await Employee.find_one(
        Employee.user_id == user_id,
        Employee.tenant_id == tenant_id
    )
    if not employee:
        return []

    leaves = await LeaveApplication.find(
        LeaveApplication.tenant_id == tenant_id,
        LeaveApplication.employee_id == employee.id
    ).sort("-applied_at").to_list()

    return leaves

@router.get("/all")
async def get_all_leaves(
    current_user = Depends(get_current_user)
):
    tenant_id = UUID(current_user["tid"])

    leaves = await LeaveApplication.find(
        LeaveApplication.tenant_id == tenant_id
    ).sort("-applied_at").to_list()

    # Enrich with employee details
    from Models.employee import Employee, Department
    
    enriched_leaves = []
    for leave in leaves:
        employee = await Employee.find_one(
            Employee.id == leave.employee_id,
            Employee.tenant_id == tenant_id
        )
        if not employee:
            employee = await Employee.find_one(
                Employee.user_id == leave.employee_id,
                Employee.tenant_id == tenant_id
            )
        
        leave_dict = leave.dict()
        if employee:
            leave_dict['employee_custom_id'] = employee.employee_number
            leave_dict['employee_email'] = employee.email_work or employee.email_personal
            leave_dict['employee_name'] = f"{employee.first_name} {employee.last_name}".strip()
            if employee.department_id:
                dept = await Department.find_one(Department.id == employee.department_id)
                leave_dict['department'] = dept.name if dept else "N/A"
            else:
                leave_dict['department'] = "N/A"
        else:
            leave_dict['employee_custom_id'] = "N/A"
            leave_dict['employee_email'] = leave.employee_name or "N/A"
            leave_dict['employee_name'] = leave.employee_name or "N/A"
            leave_dict['department'] = "N/A"
        
        enriched_leaves.append(leave_dict)

    return enriched_leaves

@router.put("/{leave_id}/action")
async def update_leave_status(
    leave_id: PydanticObjectId,
    data: LeaveActionRequest,
    current_user = Depends(get_current_user)
):
    tenant_id = UUID(current_user["tid"])
    admin_id = UUID(current_user["sub"])

    leave = await LeaveApplication.find_one(
        LeaveApplication.id == leave_id,
        LeaveApplication.tenant_id == tenant_id
    )

    if not leave:
        raise HTTPException(status_code=404, detail="Leave not found")

    if data.status not in ["Approved", "Rejected"]:
        raise HTTPException(status_code=400, detail="Invalid status")

    leave.status = data.status
    leave.updated_at = datetime.utcnow()
    leave.approved_by = admin_id

    if data.status == "Rejected":
        leave.rejection_reason = data.reason

    await leave.save()

    return {
        "message": f"Leave {data.status} successfully",
        "data": leave
    }