from beanie import Document
from typing import Optional
from datetime import datetime
from uuid import UUID

class JobRequisition(Document):
    tenant_id: UUID   # ✅ tenant isolation

    job_title: str
    hiring_manager: str
    budget_range: str | None = None

    department: str
    headcount: int
    priority: str = "Medium"  # Low / Medium / High

    status: str = "Open"  # Open / Closed / On Hold
    created_by: Optional[UUID] = None 
    created_at: datetime = datetime.utcnow()
    updated_at: datetime = datetime.utcnow()

    class Settings:
        name = "job_requisitions"