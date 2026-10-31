
from pydantic import BaseModel
from typing import List, Optional
from uuid import UUID
from datetime import datetime


class LeaveAssignmentCreate(BaseModel):
    policy_id: str
    employee_ids: List[UUID]


class LeaveAssignmentUpdate(BaseModel):
    total_days: Optional[int] = None
    remaining_days: Optional[int] = None
    status: Optional[str] = None


class LeaveAdjustmentBase(BaseModel):
    assignment_id: Optional[str] = None
    employee_id: UUID
    days: float
    reason: str
    effective_date: Optional[datetime] = None


class AddLeaveAdjustment(LeaveAdjustmentBase):
    """Schema for adding leave balance"""
    pass


class DeductLeaveAdjustment(LeaveAdjustmentBase):
    """Schema for deducting leave balance"""
    pass


class LeaveAdjustmentResponse(BaseModel):
    assignment_id: str
    employee_id: str
    employee_name: str
    days_added: Optional[float] = None
    days_deducted: Optional[float] = None
    total_days: float
    remaining_days: float
    reason: str
    effective_date: datetime
