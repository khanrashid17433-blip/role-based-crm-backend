
from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional
from uuid import UUID
from datetime import datetime
from beanie import PydanticObjectId

from Utility.auth_helpers import get_current_user

from Models.leave_assignment import LeaveAssignment
from Models.leave import LeavePolicy
from Models.employee import Department, Employee
from Models.employeeleave import LeaveApplication

from Schema.leave_assignment import (
    LeaveAssignmentCreate,
    LeaveAssignmentUpdate,
    AddLeaveAdjustment,
    DeductLeaveAdjustment
)

router = APIRouter(
    prefix="/api/leave-assignment",
    tags=["Leave Assignment"]
)

# =========================================================
# ASSIGN POLICY TO EMPLOYEE / DEPARTMENT
# =========================================================

@router.post("/assign")
async def assign_leave_policy(
    data: LeaveAssignmentCreate,
    current_user=Depends(get_current_user)
):
    tenant_id = UUID(current_user["tid"])
    admin_id = UUID(current_user["sub"])

    try:
        policy_id = PydanticObjectId(data.policy_id)
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Invalid leave policy ID"
        )

    policy = await LeavePolicy.find_one(
        LeavePolicy.id == policy_id,
        LeavePolicy.tenant_id == tenant_id
    )

    if not policy:
        raise HTTPException(
            status_code=404,
            detail="Leave policy not found"
        )

    created_assignments = []

    for employee_id in data.employee_ids:

        employee = await Employee.find_one(
            Employee.id == employee_id,
            Employee.tenant_id == tenant_id
        )

        if not employee:
            continue

        existing = await LeaveAssignment.find_one(
            LeaveAssignment.employee_id == employee_id,
            LeaveAssignment.policy_id == str(policy.id),
            LeaveAssignment.tenant_id == tenant_id
        )

        if existing:
            continue

        department = None
        if employee.department_id:
            department = await Department.find_one(
                Department.id == employee.department_id,
                Department.tenant_id == tenant_id
            )

        assignment = LeaveAssignment(
            tenant_id=tenant_id,

            policy_id=str(policy.id),
            policy_name=policy.policy_name,

            employee_id=employee.id,
            employee_name=f"{employee.first_name} {employee.last_name}".strip(),
            department=department.name if department else None,

            assigned_by=admin_id,
            assigned_at=datetime.utcnow(),

            total_days=policy.total_days,
            used_days=0,
            remaining_days=policy.total_days,

            carry_forward=policy.carry_forward_days > 0,
            paid=policy.is_paid,

            status="Active"
        )

        await assignment.insert()

        created_assignments.append(assignment)

    return {
        "message": "Policy assigned successfully",
        "count": len(created_assignments),
        "data": created_assignments
    }


# =========================================================
# GET ALL ASSIGNMENTS
# =========================================================

@router.get("/")
async def get_all_assignments(
    current_user=Depends(get_current_user)
):
    tenant_id = UUID(current_user["tid"])

    assignments = await LeaveAssignment.find(
        LeaveAssignment.tenant_id == tenant_id
    ).sort("-assigned_at").to_list()

    return assignments


# =========================================================
# GET MY ASSIGNED POLICIES
# =========================================================

@router.get("/my")
async def get_my_assignments(
    current_user=Depends(get_current_user)
):
    tenant_id = UUID(current_user["tid"])
    user_id = UUID(current_user["sub"])

    employee = await Employee.find_one(
        Employee.user_id == user_id,
        Employee.tenant_id == tenant_id
    )
    if not employee:
        return []

    assignments = await LeaveAssignment.find(
        LeaveAssignment.tenant_id == tenant_id,
        LeaveAssignment.employee_id == employee.id
    ).to_list()

    return assignments


# =========================================================
# GET LEAVE BALANCE - HR/ADMIN VIEW (all employees)
# MUST BE BEFORE /{assignment_id}
# =========================================================

@router.get("/leave-balance")
async def get_all_leave_balances(
    department: Optional[str] = None,
    leave_type: Optional[str] = None,
    search: Optional[str] = None,
    current_user=Depends(get_current_user)
):
    tenant_id = UUID(current_user["tid"])

    filters = [
        LeaveAssignment.tenant_id == tenant_id
    ]

    if department:
        filters.append(
            LeaveAssignment.department == department
        )

    if leave_type:
        filters.append(
            LeaveAssignment.policy_name == leave_type
        )

    assignments = await LeaveAssignment.find(
        *filters
    ).to_list()

    response = []

    for assignment in assignments:

        if search:
            employee_name = (assignment.employee_name or "")
            if search.lower() not in employee_name.lower():
                continue

        employee = await Employee.find_one(
            Employee.id == assignment.employee_id,
            Employee.tenant_id == tenant_id
        )
        employee_custom_id = employee.employee_number if employee else "N/A"

        employee_ids = [assignment.employee_id]
        if employee and employee.user_id:
            employee_ids.append(employee.user_id)

        approved_leaves = await LeaveApplication.find(
            LeaveApplication.tenant_id == tenant_id,
            {"employee_id": {"$in": employee_ids}},
            LeaveApplication.status == "Approved",
            LeaveApplication.leave_type == assignment.policy_name
        ).to_list()

        used_days = sum(
            leave.total_days
            for leave in approved_leaves
        )

        balance = (assignment.total_days - used_days)

        response.append({
            "assignment_id": str(assignment.id),
            "id": str(assignment.id),
            "policy_id": assignment.policy_id,
            "employee_id": str(assignment.employee_id),
            "employee_custom_id": employee_custom_id,
            "employee_number": employee_custom_id,
            "employee_name": assignment.employee_name,
            "department": assignment.department,
            "leave_type": assignment.policy_name,
            "policy_name": assignment.policy_name,
            "entitled": assignment.total_days,
            "total_days": assignment.total_days,
            "used": used_days,
            "used_days": used_days,
            "balance": balance,
            "remaining": balance,
            "remaining_days": balance,
            "paid": assignment.paid,
            "carry_forward": assignment.carry_forward,
            "status": assignment.status
        })

    return {
        "total_records": len(response),
        "data": response
    }


# =========================================================
# GET MY LEAVE BALANCE - Employee self-service view
# MUST BE BEFORE /{assignment_id}
# =========================================================

@router.get("/my-balance")
async def get_my_leave_balance(
    current_user=Depends(get_current_user)
):
    """Return the logged-in employee's leave balance per policy,
    with used_days dynamically computed from approved LeaveApplications."""

    tenant_id = UUID(current_user["tid"])
    user_id = UUID(current_user["sub"])

    employee = await Employee.find_one(
        Employee.user_id == user_id,
        Employee.tenant_id == tenant_id
    )
    if not employee:
        return {
            "total_records": 0,
            "data": []
        }

    assignments = await LeaveAssignment.find(
        LeaveAssignment.tenant_id == tenant_id,
        LeaveAssignment.employee_id == employee.id
    ).to_list()

    response = []

    for assignment in assignments:
        employee_ids = [assignment.employee_id]
        if employee.user_id:
            employee_ids.append(employee.user_id)

        approved_leaves = await LeaveApplication.find(
            LeaveApplication.tenant_id == tenant_id,
            {"employee_id": {"$in": employee_ids}},
            LeaveApplication.status == "Approved",
            LeaveApplication.leave_type == assignment.policy_name
        ).to_list()

        used_days = sum(leave.total_days for leave in approved_leaves)
        balance = assignment.total_days - used_days

        response.append({
            "assignment_id": str(assignment.id),
            "id": str(assignment.id),
            "policy_id": assignment.policy_id,
            "policy_name": assignment.policy_name,
            "type": assignment.policy_name,
            "leave_type": assignment.policy_name,
            "total": assignment.total_days,
            "total_days": assignment.total_days,
            "used": used_days,
            "used_days": used_days,
            "remaining": balance,
            "remaining_days": balance,
            "balance": balance,
            "paid": assignment.paid,
            "status": assignment.status,
        })

    return response


# =========================================================
# GET SINGLE ASSIGNMENT
# =========================================================

@router.get("/{assignment_id}")
async def get_single_assignment(
    assignment_id: PydanticObjectId,
    current_user=Depends(get_current_user)
):
    tenant_id = UUID(current_user["tid"])

    assignment = await LeaveAssignment.find_one(
        LeaveAssignment.id == assignment_id,
        LeaveAssignment.tenant_id == tenant_id
    )

    if not assignment:
        raise HTTPException(
            status_code=404,
            detail="Assignment not found"
        )

    return assignment


# =========================================================
# UPDATE ASSIGNMENT
# =========================================================

@router.put("/{assignment_id}")
async def update_assignment(
    assignment_id: PydanticObjectId,
    data: LeaveAssignmentUpdate,
    current_user=Depends(get_current_user)
):
    tenant_id = UUID(current_user["tid"])

    assignment = await LeaveAssignment.find_one(
        LeaveAssignment.id == assignment_id,
        LeaveAssignment.tenant_id == tenant_id
    )

    if not assignment:
        raise HTTPException(
            status_code=404,
            detail="Assignment not found"
        )

    if data.total_days is not None:
        assignment.total_days = data.total_days

    if data.remaining_days is not None:
        assignment.remaining_days = data.remaining_days

    if data.status:
        assignment.status = data.status

    assignment.updated_at = datetime.utcnow()

    await assignment.save()

    return {
        "message": "Assignment updated successfully",
        "data": assignment
    }


# =========================================================
# ADD LEAVE BALANCE (Admin adjustment)
# =========================================================

@router.post("/add-leave")
async def add_leave_balance(
    data: AddLeaveAdjustment,
    current_user=Depends(get_current_user)
):
    tenant_id = UUID(current_user["tid"])
    admin_id = UUID(current_user["sub"])

    if data.days <= 0:
        raise HTTPException(
            status_code=400,
            detail="Days must be greater than 0"
        )

    if not data.reason:
        raise HTTPException(
            status_code=400,
            detail="Reason is required"
        )

    assignment = None
    if data.assignment_id:
        try:
            assignment_id = PydanticObjectId(data.assignment_id)
        except Exception:
            raise HTTPException(
                status_code=400,
                detail="Invalid assignment ID"
            )

        assignment = await LeaveAssignment.find_one(
            LeaveAssignment.id == assignment_id,
            LeaveAssignment.employee_id == data.employee_id,
            LeaveAssignment.tenant_id == tenant_id,
            LeaveAssignment.status == "Active"
        )
    else:
        assignment = await LeaveAssignment.find_one(
            LeaveAssignment.employee_id == data.employee_id,
            LeaveAssignment.tenant_id == tenant_id,
            LeaveAssignment.status == "Active"
        )

    if not assignment:
        raise HTTPException(
            status_code=404,
            detail="No active leave assignment found for this employee"
        )

    assignment.total_days += data.days
    assignment.remaining_days += data.days
    assignment.updated_at = datetime.utcnow()

    await assignment.save()

    from Models.security_event import SecurityEvent

    audit_log = SecurityEvent(
        tenant_id=tenant_id,
        user_id=admin_id,
        event_type="LEAVE_ADDED",
        description=f"Added {data.days} leave days to {assignment.employee_name}. Reason: {data.reason}",
        resource_type="LeaveAssignment",
        resource_id=str(assignment.id),
        timestamp=datetime.utcnow()
    )

    await audit_log.insert()

    return {
        "message": "Leave balance added successfully",
        "data": {
            "assignment_id": str(assignment.id),
            "employee_id": str(assignment.employee_id),
            "employee_name": assignment.employee_name,
            "days_added": data.days,
            "total_days": assignment.total_days,
            "remaining_days": assignment.remaining_days,
            "reason": data.reason,
            "effective_date": data.effective_date or datetime.utcnow()
        }
    }


# =========================================================
# DEDUCT LEAVE BALANCE (Admin adjustment)
# =========================================================

@router.post("/deduct-leave")
async def deduct_leave_balance(
    data: DeductLeaveAdjustment,
    current_user=Depends(get_current_user)
):
    tenant_id = UUID(current_user["tid"])
    admin_id = UUID(current_user["sub"])

    if data.days <= 0:
        raise HTTPException(
            status_code=400,
            detail="Days must be greater than 0"
        )

    if not data.reason:
        raise HTTPException(
            status_code=400,
            detail="Reason is required"
        )

    assignment = None
    if data.assignment_id:
        try:
            assignment_id = PydanticObjectId(data.assignment_id)
        except Exception:
            raise HTTPException(
                status_code=400,
                detail="Invalid assignment ID"
            )

        assignment = await LeaveAssignment.find_one(
            LeaveAssignment.id == assignment_id,
            LeaveAssignment.employee_id == data.employee_id,
            LeaveAssignment.tenant_id == tenant_id,
            LeaveAssignment.status == "Active"
        )
    else:
        assignment = await LeaveAssignment.find_one(
            LeaveAssignment.employee_id == data.employee_id,
            LeaveAssignment.tenant_id == tenant_id,
            LeaveAssignment.status == "Active"
        )

    if not assignment:
        raise HTTPException(
            status_code=404,
            detail="No active leave assignment found for this employee"
        )

    if assignment.total_days < data.days:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient leave balance. Available: {assignment.total_days} days"
        )

    assignment.total_days -= data.days
    assignment.remaining_days -= data.days
    assignment.updated_at = datetime.utcnow()

    await assignment.save()

    from Models.security_event import SecurityEvent

    audit_log = SecurityEvent(
        tenant_id=tenant_id,
        user_id=admin_id,
        event_type="LEAVE_DEDUCTED",
        description=f"Deducted {data.days} leave days from {assignment.employee_name}. Reason: {data.reason}",
        resource_type="LeaveAssignment",
        resource_id=str(assignment.id),
        timestamp=datetime.utcnow()
    )

    await audit_log.insert()

    return {
        "message": "Leave balance deducted successfully",
        "data": {
            "assignment_id": str(assignment.id),
            "employee_id": str(assignment.employee_id),
            "employee_name": assignment.employee_name,
            "days_deducted": data.days,
            "total_days": assignment.total_days,
            "remaining_days": assignment.remaining_days,
            "reason": data.reason,
            "effective_date": data.effective_date or datetime.utcnow()
        }
    }


# =========================================================
# DELETE / UNASSIGN POLICY
# =========================================================

@router.delete("/{assignment_id}")
async def delete_assignment(
    assignment_id: PydanticObjectId,
    current_user=Depends(get_current_user)
):
    tenant_id = UUID(current_user["tid"])

    assignment = await LeaveAssignment.find_one(
        LeaveAssignment.id == assignment_id,
        LeaveAssignment.tenant_id == tenant_id
    )

    if not assignment:
        raise HTTPException(
            status_code=404,
            detail="Assignment not found"
        )

    await assignment.delete()

    return {
        "message": "Policy unassigned successfully"
    }
