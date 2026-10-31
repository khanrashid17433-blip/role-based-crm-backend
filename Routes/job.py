from fastapi import APIRouter, HTTPException, status, Depends
from datetime import datetime
from beanie import PydanticObjectId
from Utility.auth_helpers import verify_tenant_admin
from uuid import UUID
import logging

logger = logging.getLogger(__name__)

# ✅ Model
from Models.job import JobRequisition

# ✅ Schemas
from Schema.job import (
    JobRequisitionCreate,
    JobRequisitionUpdate
)

router = APIRouter(
    prefix="/api/job-requisition",
    tags=["Job Requisition"]
)

# ✅ Helper (safe UUID conversion)
def safe_uuid(value, field_name="id"):
    try:
        return UUID(value)
    except Exception:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {field_name} format"
        )


# ✅ CREATE Job Requisition
@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_job_requisition(
    data: JobRequisitionCreate,
    current_user=Depends(verify_tenant_admin)
):
    try:
        # ✅ Tenant check
        tid = current_user.get("tid")
        if not tid:
            raise HTTPException(status_code=401, detail="Tenant ID missing")

        tenant_id = safe_uuid(tid, "tenant_id")

        # ✅ Optional user_id (NO CRASH 🔥)
        uid = current_user.get("uid")
        user_id = None

        if uid:
            try:
                user_id = UUID(uid)
            except:
                logger.warning("Invalid UID format, setting created_by=None")

        job = JobRequisition(
            **data.dict(),
            tenant_id=tenant_id,
            created_by=user_id
        )

        await job.insert()

        return {
            "message": "Job Requisition Created Successfully",
            "data": job
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create job failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")


# ✅ GET ALL (tenant safe)
@router.get("/")
async def get_all_jobs(
    current_user=Depends(verify_tenant_admin)
):
    tid = current_user.get("tid")
    tenant_id = safe_uuid(tid, "tenant_id")

    jobs = await JobRequisition.find(
        JobRequisition.tenant_id == tenant_id
    ).to_list()

    return jobs


# ✅ GET SINGLE (tenant safe 🔐)
@router.get("/{job_id}")
async def get_job(
    job_id: str,
    current_user=Depends(verify_tenant_admin)
):
    tenant_id = UUID(current_user.get("tid"))
    obj_id = PydanticObjectId(job_id)

    job = await JobRequisition.find_one(
        JobRequisition.id == obj_id,
        JobRequisition.tenant_id == tenant_id
    )

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return job

# ✅ UPDATE (tenant safe)
@router.put("/{job_id}")
async def update_job(
    job_id: str,
    data: JobRequisitionUpdate,
    current_user=Depends(verify_tenant_admin)
):
    tenant_id = safe_uuid(current_user.get("tid"), "tenant_id")
    obj_id = PydanticObjectId(job_id)

    job = await JobRequisition.find_one(
        JobRequisition.id == obj_id,
        JobRequisition.tenant_id == tenant_id
    )

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    update_data = data.dict(exclude_unset=True)

    for key, value in update_data.items():
        setattr(job, key, value)

    job.updated_at = datetime.utcnow()

    await job.save()

    return job


# ✅ DELETE (tenant safe)
@router.delete("/{job_id}")
async def delete_job(
    job_id: str,
    current_user=Depends(verify_tenant_admin)
):
    tenant_id = safe_uuid(current_user.get("tid"), "tenant_id")
    obj_id = PydanticObjectId(job_id)

    job = await JobRequisition.find_one(
        JobRequisition.id == obj_id,
        JobRequisition.tenant_id == tenant_id
    )

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    await job.delete()

    return {"message": "Deleted successfully"}