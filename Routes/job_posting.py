from fastapi import APIRouter, HTTPException, status, Depends
from datetime import datetime
from beanie import PydanticObjectId
from uuid import UUID
import logging

from Utility.auth_helpers import verify_tenant_admin

# ✅ Model
from Models.job_posting import JobPosting

# ✅ Schema
from Schema.job_posting import (
    JobPostingCreate,
    JobPostingUpdate
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/job-postings",
    tags=["Job Postings"]
)


# ✅ Helper
def safe_uuid(value, field_name="id"):
    try:
        return UUID(value)
    except Exception:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {field_name} format"
        )


# ==========================================
# CREATE JOB POSTING
# ==========================================
@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_job_posting(
    data: JobPostingCreate,
    current_user=Depends(verify_tenant_admin)
):
    try:
        tid = current_user.get("tid")

        if not tid:
            raise HTTPException(
                status_code=401,
                detail="Tenant ID missing"
            )

        tenant_id = safe_uuid(tid, "tenant_id")

        uid = current_user.get("uid")
        user_id = None

        if uid:
            try:
                user_id = UUID(uid)
            except:
                logger.warning(
                    "Invalid UID format, setting created_by=None"
                )

        job = JobPosting(
            **data.dict(),
            tenant_id=tenant_id,
            created_by=user_id,
            status="Published"
        )

        await job.insert()

        return {
            "message": "Job Posted Successfully",
            "data": job
        }

    except HTTPException:
        raise

    except Exception as e:
        logger.error(
            f"Create job posting failed: {str(e)}",
            exc_info=True
        )

        raise HTTPException(
            status_code=500,
            detail="Internal Server Error"
        )


# ==========================================
# GET ALL JOBS
# ==========================================
@router.get("/")
async def get_all_job_postings(
    current_user=Depends(verify_tenant_admin)
):
    tenant_id = safe_uuid(
        current_user.get("tid"),
        "tenant_id"
    )

    jobs = await JobPosting.find(
        JobPosting.tenant_id == tenant_id
    ).to_list()

    return jobs


# ==========================================
# GET SINGLE JOB
# ==========================================
@router.get("/{job_id}")
async def get_job_posting(
    job_id: str,
    current_user=Depends(verify_tenant_admin)
):
    tenant_id = safe_uuid(
        current_user.get("tid"),
        "tenant_id"
    )

    obj_id = PydanticObjectId(job_id)

    job = await JobPosting.find_one(
        JobPosting.id == obj_id,
        JobPosting.tenant_id == tenant_id
    )

    if not job:
        raise HTTPException(
            status_code=404,
            detail="Job Posting not found"
        )

    return job


# ==========================================
# UPDATE JOB
# ==========================================
@router.put("/{job_id}")
async def update_job_posting(
    job_id: str,
    data: JobPostingUpdate,
    current_user=Depends(verify_tenant_admin)
):
    tenant_id = safe_uuid(
        current_user.get("tid"),
        "tenant_id"
    )

    obj_id = PydanticObjectId(job_id)

    job = await JobPosting.find_one(
        JobPosting.id == obj_id,
        JobPosting.tenant_id == tenant_id
    )

    if not job:
        raise HTTPException(
            status_code=404,
            detail="Job Posting not found"
        )

    update_data = data.dict(
        exclude_unset=True
    )

    for key, value in update_data.items():
        setattr(job, key, value)

    job.updated_at = datetime.utcnow()

    await job.save()

    return {
        "message": "Job Posting Updated Successfully",
        "data": job
    }


# ==========================================
# DELETE JOB
# ==========================================
@router.delete("/{job_id}")
async def delete_job_posting(
    job_id: str,
    current_user=Depends(verify_tenant_admin)
):
    tenant_id = safe_uuid(
        current_user.get("tid"),
        "tenant_id"
    )

    obj_id = PydanticObjectId(job_id)

    job = await JobPosting.find_one(
        JobPosting.id == obj_id,
        JobPosting.tenant_id == tenant_id
    )

    if not job:
        raise HTTPException(
            status_code=404,
            detail="Job Posting not found"
        )

    await job.delete()

    return {
        "message": "Job Posting Deleted Successfully"
    }