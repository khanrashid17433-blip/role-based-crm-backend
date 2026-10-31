from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from typing import Dict, Any, List
from uuid import UUID
import logging
import os
import shutil

from Schema.pm import (
    ProjectCreateRequest, ProjectUpdateRequest,
    TaskCreateRequest, TaskUpdateRequest, TaskTimeLogRequest
)
from Services.pm_service import PMService
from Utility.auth_helpers import get_current_user

logger = logging.getLogger(__name__)

# Directory to save task attachments
ATTACHMENTS_DIR = "static/task_attachments"
os.makedirs(ATTACHMENTS_DIR, exist_ok=True)

router = APIRouter(prefix="/api/pm", tags=["Project & Task Management"])

# --- PROJECTS ---

@router.post("/projects", summary="Create Project", status_code=status.HTTP_201_CREATED)
async def create_project(data: ProjectCreateRequest, current_user = Depends(get_current_user)):
    try:
        tenant_id = UUID(current_user.get('tid'))
        user_id = UUID(current_user.get('sub'))
        project = await PMService.create_project(tenant_id, user_id, data)
        return {"message": "Project created", "project_id": str(project.id)}
    except Exception as e:
        logger.error(f"Failed to create project: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))

@router.patch("/projects/{project_id}", summary="Update Project")
async def update_project(project_id: str, data: ProjectUpdateRequest, current_user = Depends(get_current_user)):
    try:
        tenant_id = UUID(current_user.get('tid'))
        user_id = UUID(current_user.get('sub'))
        project = await PMService.update_project(tenant_id, UUID(project_id), data, user_id)
        return {"message": "Project updated", "project_id": str(project.id)}
    except Exception as e:
        import traceback
        traceback.print_exc()
        logger.error(f"Failed to update project {project_id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


# --- TASKS ---

@router.post("/tasks", summary="Create Task", status_code=status.HTTP_201_CREATED)
async def create_task(data: TaskCreateRequest, current_user = Depends(get_current_user)):
    try:
        tenant_id = UUID(current_user.get('tid'))
        user_id = UUID(current_user.get('sub'))
        task = await PMService.create_task(tenant_id, user_id, data)
        return {"message": "Task created", "task_id": str(task.id)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.patch("/tasks/{task_id}/status", summary="Update Task Status or Priority")
async def update_task_status(task_id: str, data: TaskUpdateRequest, current_user = Depends(get_current_user)):
    try:
        if not data.status and not data.priority:
            raise ValueError("Status or priority is required")
        tenant_id = UUID(current_user.get('tid'))
        task = await PMService.update_task_status(tenant_id, UUID(task_id), data.status, data.priority)
        return {"message": "Task updated"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/tasks/{task_id}/time", summary="Log Time on Task")
async def log_task_time(task_id: str, data: TaskTimeLogRequest, current_user = Depends(get_current_user)):
    try:
        tenant_id = UUID(current_user.get('tid'))
        user_id = UUID(current_user.get('sub'))
        entry = await PMService.log_time(tenant_id, UUID(task_id), user_id, data)
        return {"message": "Time logged successfully", "entry_id": str(entry.id)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/dashboard-summary", summary="Get PM Dashboard Summary")
async def get_pm_dashboard_summary(current_user = Depends(get_current_user)):
    try:
        tenant_id = UUID(current_user.get('tid'))
        user_id = UUID(current_user.get('sub'))
        summary = await PMService.get_dashboard_summary(tenant_id, user_id)
        return summary
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/members", summary="Get Tenant Members for PM")
async def get_pm_members(current_user = Depends(get_current_user)):
    try:
        tenant_id = UUID(current_user.get('tid'))
        members = await PMService.get_members(tenant_id)
        return members
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/projects", summary="List Tenant Projects")
async def list_pm_projects(current_user = Depends(get_current_user)):
    try:
        tenant_id = UUID(current_user.get('tid'))
        user_id = UUID(current_user.get('sub'))
        summary = await PMService.get_dashboard_summary(tenant_id, user_id)
        return summary.get("projects", [])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tasks", summary="List Tenant Tasks")
async def list_pm_tasks(current_user = Depends(get_current_user)):
    try:
        tenant_id = UUID(current_user.get('tid'))
        user_id = UUID(current_user.get('sub'))
        summary = await PMService.get_dashboard_summary(tenant_id, user_id)
        return summary.get("tasks", [])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/employee/summary", summary="Get Employee Project & Tasks Summary")
async def get_employee_pm_summary(current_user = Depends(get_current_user)):
    try:
        tenant_id = UUID(current_user.get('tid'))
        user_id = UUID(current_user.get('sub'))
        summary = await PMService.get_employee_summary(tenant_id, user_id)
        return summary
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/tasks/{task_id}/comments", summary="Add Comment to Task")
async def add_task_comment(task_id: str, data: Dict[str, str], current_user = Depends(get_current_user)):
    try:
        tenant_id = UUID(current_user.get('tid'))
        user_id = UUID(current_user.get('sub'))
        text = data.get("text")
        if not text or not text.strip():
            raise ValueError("Comment text cannot be empty")
        
        comment = await PMService.add_task_comment(tenant_id, UUID(task_id), user_id, text.strip())
        return comment
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/tasks/{task_id}/attachments", summary="Upload Attachment to Task")
async def upload_task_attachment(task_id: str, file: UploadFile = File(...), current_user = Depends(get_current_user)):
    try:
        tenant_id = UUID(current_user.get('tid'))
        user_id = UUID(current_user.get('sub'))
        
        # Save file locally
        os.makedirs(os.path.join(ATTACHMENTS_DIR, task_id), exist_ok=True)
        file_path = os.path.join(ATTACHMENTS_DIR, task_id, file.filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        file_url = f"/static/task_attachments/{task_id}/{file.filename}"
        
        attachment = await PMService.add_task_attachment(
            tenant_id, UUID(task_id), user_id, 
            file.filename, file.size or 0, file.content_type or "application/octet-stream", 
            file_url
        )
        return attachment
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/tasks/{task_id}/attachments/{attachment_id}", summary="Delete Attachment from Task")
async def delete_task_attachment(task_id: str, attachment_id: str, current_user = Depends(get_current_user)):
    try:
        tenant_id = UUID(current_user.get('tid'))
        await PMService.delete_task_attachment(tenant_id, UUID(task_id), attachment_id)
        return {"message": "Attachment deleted"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
