from beanie import Document
from datetime import datetime
from uuid import UUID

class LeavePolicy(Document):
    tenant_id: UUID   # ✅ ADD THIS
    policy_name: str
    leave_type: str
    total_days: int
    carry_forward_days: int = 0
    status: str = "Active"
    is_paid: bool = True
    created_at: datetime = datetime.utcnow()
    updated_at: datetime = datetime.utcnow() 

    class Settings:
        name = "leave_policies"