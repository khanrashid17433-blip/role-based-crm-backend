from beanie import Document
from typing import Optional
from datetime import datetime
from uuid import UUID


class JobPosting(Document):
    tenant_id: UUID

    job_title: str
    location: str
    job_description: str

    publish_company_website: bool = False
    publish_linkedin: bool = False
    publish_indeed: bool = False
    publish_naukri: bool = False

    status: str = "Draft"  # Draft / Published / Closed

    created_by: Optional[UUID] = None

    created_at: datetime = datetime.utcnow()
    updated_at: datetime = datetime.utcnow()

    class Settings:
        name = "job_postings"