from beanie import Document
from uuid import UUID
from datetime import datetime
from typing import Optional


class LeaveAssignment(Document):

    tenant_id: UUID

    # POLICY
    policy_id: str
    policy_name: str

    # EMPLOYEE
    employee_id: UUID
    employee_name: str
    department: Optional[str]

    # LEAVE DETAILS
    total_days: int
    used_days: int = 0
    remaining_days: int

    carry_forward: bool = False
    paid: bool = True

    # STATUS
    status: str = "Active"

    # AUDIT
    assigned_by: UUID
    assigned_at: datetime = datetime.utcnow()
    updated_at: Optional[datetime] = None

    class Settings:
        name = "leave_assignments"