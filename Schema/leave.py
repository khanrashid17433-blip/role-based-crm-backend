from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class LeavePolicyBase(BaseModel):
    policy_name: str
    leave_type: str
    total_days: int
    carry_forward_days: int = 0
    status: str = "Active"
    is_paid: bool = True


class LeavePolicyCreate(LeavePolicyBase):
    pass


class LeavePolicyUpdate(BaseModel):
    policy_name: Optional[str] = None
    leave_type: Optional[str] = None
    total_days: Optional[int] = None
    carry_forward_days: Optional[int] = None
    status: Optional[str] = None
    is_paid: Optional[bool] = None


class LeavePolicyResponse(BaseModel):
    id: str
    tenant_id: Optional[str] = None   # ⭐ important (add this)
    policy_name: str
    leave_type: str
    total_days: int
    carry_forward_days: int
    status: str
    is_paid: bool
    created_at: datetime