from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


# 🔹 Base
class JobPostingBase(BaseModel):
    job_title: str
    location: str
    job_description: str

    publish_company_website: bool = False
    publish_linkedin: bool = False
    publish_indeed: bool = False
    publish_naukri: bool = False


# 🔹 Create
class JobPostingCreate(JobPostingBase):
    pass


# 🔹 Update
class JobPostingUpdate(BaseModel):
    job_title: Optional[str] = None
    location: Optional[str] = None
    job_description: Optional[str] = None

    status: Optional[str] = None  # Draft / Published / Closed

    publish_company_website: Optional[bool] = None
    publish_linkedin: Optional[bool] = None
    publish_indeed: Optional[bool] = None
    publish_naukri: Optional[bool] = None


# 🔹 Response
class JobPostingResponse(BaseModel):
    id: str
    tenant_id: Optional[str] = None

    job_title: str
    location: str
    job_description: str

    publish_company_website: bool
    publish_linkedin: bool
    publish_indeed: bool
    publish_naukri: bool

    status: str
    created_at: datetime

    class Config:
        orm_mode = True