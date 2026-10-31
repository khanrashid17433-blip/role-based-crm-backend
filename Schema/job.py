from pydantic import BaseModel
from typing import Optional
from datetime import datetime


# 🔹 Base
class JobRequisitionBase(BaseModel):
    job_title: str
    hiring_manager: str
    budget_range: Optional[str] = None
    department: str
    headcount: int
    priority: str = "Medium"
    status: str = "Open"


# 🔹 Create
class JobRequisitionCreate(JobRequisitionBase):
    pass


# 🔹 Update
class JobRequisitionUpdate(BaseModel):
    job_title: Optional[str] = None
    hiring_manager: Optional[str] = None
    budget_range: Optional[str] = None
    department: Optional[str] = None
    headcount: Optional[int] = None
    priority: Optional[str] = None
    status: Optional[str] = None


# 🔹 Response
class JobRequisitionResponse(BaseModel):
    id: str
    tenant_id: Optional[str] = None   # ⭐ important
    job_title: str
    hiring_manager: str
    budget_range: Optional[str]
    department: str
    headcount: int
    priority: str
    status: str
    created_at: datetime

    class Config:
        orm_mode = True