from beanie import Document
from datetime import datetime, date
from pydantic import Field
from uuid import UUID
from typing import Optional

class LeaveApplication(Document):
    tenant_id: UUID

    employee_id: UUID
    employee_name: Optional[str] = None

    leave_type: str
    start_date: datetime   # ✅ बदलो
    end_date: datetime   
    total_days: Optional[int] = None

    reason: str
    attachment: str | None = None

    status: str = "Pending"  # Pending / Approved / Rejected

    applied_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    approved_by: UUID | None = None
    rejection_reason: str | None = None

    class Settings:
        name = "leave_applications"