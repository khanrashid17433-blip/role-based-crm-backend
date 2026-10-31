from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from typing import Dict, Any, Optional, List
from uuid import UUID
import logging
import os
import shutil
from datetime import datetime

from Schema.task import TaskCreateRequest, TaskUpdateRequest, TaskCommentRequest, TaskFilterParams
from Services.task_service import TaskService
from Utility.auth_helpers import get_current_user, verify_platform_admin
from Models.crm_task import CrmTask
from Models.crm import CrmLead, CrmDeal
from Models.crm_contacts import CrmContact

logger = logging.getLogger(__name__)

# Directory to save task attachments
TASK_ATTACHMENTS_DIR = "static/task_attachments"
os.makedirs(TASK_ATTACHMENTS_DIR, exist_ok=True)

router = APIRouter(prefix="/api/crm/tasks", tags=["CRM Tasks"])

async def resolve_associated_record(task: CrmTask) -> tuple:
    """Resolve associated record name and module type from task associations.
    Returns (associated_name, associated_type)"""
    if task.lead_id:
        try:
            lead = await CrmLead.find_one(CrmLead.id == task.lead_id)
            if lead:
                name = f"{lead.first_name} {lead.last_name}".strip() or lead.company_name or "Lead"
                return name, "Lead"
        except Exception:
            pass
    if task.contact_id:
        try:
            contact = await CrmContact.find_one(CrmContact.id == task.contact_id)
            if contact:
                name = f"{contact.first_name} {contact.last_name}".strip() or "Contact"
                return name, "Contact"
        except Exception:
            pass
    if task.deal_id:
        try:
            deal = await CrmDeal.find_one(CrmDeal.id == task.deal_id)
            if deal:
                return deal.deal_name or "Deal", "Deal"
        except Exception:
            pass
    if task.company_id:
        return "Company", "Company"
    return None, None

async def resolve_associated_id(task: CrmTask) -> str:
    """Get the associated record ID for linking"""
    return str(task.lead_id) if task.lead_id else str(task.contact_id) if task.contact_id else str(task.deal_id) if task.deal_id else str(task.company_id) if task.company_id else None

async def resolve_associated_type_str(task: CrmTask) -> str:
    """Get the associated module type string"""
    if task.lead_id: return "lead"
    if task.contact_id: return "contact"
    if task.deal_id: return "deal"
    if task.company_id: return "company"
    return None

async def resolve_owner_name(task: CrmTask) -> tuple:
    """Resolve owner and assigned user names with employee details. 
    Returns (owner_name, assigned_name, assigned_employee_id, assigned_role)."""
    owner_name = None
    assigned_name = None
    assigned_employee_id = None
    assigned_role = None
    
    if task.owner_id:
        try:
            from Models.tenant_user import User
            from Models.employee import Employee
            owner = await User.find_one(User.id == task.owner_id)
            if owner:
                # Try to get richer name from employee record
                emp_name = None
                try:
                    emp = await Employee.find_one(Employee.user_id == owner.id)
                    if emp:
                        emp_name = f"{emp.first_name} {emp.last_name}".strip()
                except Exception:
                    pass
                
                owner_name = emp_name or f"{owner.first_name} {owner.last_name}".strip() or str(task.owner_id)[:8]
        except Exception:
            pass
    
    if task.assigned_to:
        try:
            from Models.tenant_user import User
            from Models.employee import Employee
            assigned = await User.find_one(User.id == task.assigned_to)
            if assigned:
                # Try to get richer name and details from employee record
                emp_name = None
                try:
                    emp = await Employee.find_one(Employee.user_id == assigned.id)
                    if emp:
                        emp_name = f"{emp.first_name} {emp.last_name}".strip()
                        assigned_employee_id = emp.employee_number
                except Exception:
                    pass
                
                assigned_name = emp_name or f"{assigned.first_name} {assigned.last_name}".strip() or str(task.assigned_to)[:8]
                assigned_role = getattr(assigned, 'role', None)
        except Exception:
            pass
    
    return owner_name, assigned_name, assigned_employee_id, assigned_role


async def serialize_task(task: CrmTask) -> dict:
    """Serialize a task object to a dictionary"""
    owner_name, assigned_name, assigned_employee_id, assigned_role = await resolve_owner_name(task)
    
    return {
        "id": str(task.id),
        "tenant_id": str(task.tenant_id),
        "title": task.title,
        "description": task.description,
        "type": task.type,
        "priority": task.priority,
        "status": task.status,
        "owner_id": str(task.owner_id) if task.owner_id else None,
        "owner_name": owner_name,
        "assigned_to": str(task.assigned_to) if task.assigned_to else None,
        "assigned_to_name": assigned_name,
        "assigned_to_employee_id": assigned_employee_id,
        "assigned_to_role": assigned_role,
        "lead_id": str(task.lead_id) if task.lead_id else None,
        "contact_id": str(task.contact_id) if task.contact_id else None,
        "deal_id": str(task.deal_id) if task.deal_id else None,
        "company_id": str(task.company_id) if task.company_id else None,
        "due_date": task.due_date.isoformat() if task.due_date else None,
        "due_time": task.due_time,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "reminder_time": task.reminder_time,
        "reminder_type": task.reminder_type,
        "reminder_sent": task.reminder_sent,
        "repeat": task.repeat,
        "attachments": task.attachments,
        "comments": task.comments,
        "checklist": task.checklist,
        "notes": task.notes,
        "estimated_time": task.estimated_time,
        "created_by": str(task.created_by) if task.created_by else None,
        "updated_by": str(task.updated_by) if task.updated_by else None,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
        "archived_at": task.archived_at.isoformat() if task.archived_at else None,
        "associated_name": None,
        "associated_type": None,
        "associated_id": None,
    }

# ── Task CRUD ──

@router.get("/employees", summary="Get Assignable Employees/Users for Tasks")
async def get_task_employees(current_user=Depends(verify_platform_admin)):
    """Return all tenant users that can be assigned to a task (for dropdown)"""
    try:
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        from Models.tenant_user import User
        from Models.employee import Employee
        
        users = await User.find(User.tenant_id == tenant_id).to_list()
        result = []
        seen_ids = set()
        
        for user in users:
            uid = str(user.id)
            if uid in seen_ids:
                continue
            seen_ids.add(uid)
            
            # Try to get richer name and employee_number from employee record
            emp_name = None
            employee_number = None
            try:
                emp = await Employee.find_one(
                    Employee.user_id == user.id,
                    Employee.tenant_id == tenant_id
                )
                if emp:
                    emp_name = f"{emp.first_name or ''} {emp.last_name or ''}".strip()
                    employee_number = emp.employee_number
            except Exception:
                pass
            
            name = emp_name or f"{getattr(user, 'first_name', '') or ''} {getattr(user, 'last_name', '') or ''}".strip()
            if not name:
                name = user.email.split('@')[0] if user.email else uid[:8]
            
            result.append({
                "id": uid,
                "name": name,
                "email": user.email or "",
                "role": getattr(user, 'role', '') or "",
                "employee_id": employee_number or ""
            })
        
        return sorted(result, key=lambda x: x["name"].lower())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/counts", summary="Get Task Counts")
async def get_task_counts(current_user=Depends(verify_platform_admin)):
    """Get task counts for dashboard cards"""
    try:
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        user_id = UUID(current_user.get('sub'))
        counts = await TaskService.get_task_counts(tenant_id, user_id)
        return counts
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("", summary="List Tasks")
async def list_tasks(
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    type: Optional[str] = Query(None),
    owner_id: Optional[str] = Query(None),
    assigned_to: Optional[str] = Query(None),
    lead_id: Optional[str] = Query(None),
    contact_id: Optional[str] = Query(None),
    deal_id: Optional[str] = Query(None),
    company_id: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    associated_type: Optional[str] = Query(None),
    due_date_from: Optional[str] = Query(None),
    due_date_to: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
    current_user=Depends(verify_platform_admin)
):
    try:
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        
        filters = {}
        if status: filters["status"] = status
        if priority: filters["priority"] = priority
        if type: filters["type"] = type
        if owner_id: filters["owner_id"] = owner_id
        if assigned_to: filters["assigned_to"] = assigned_to
        if lead_id: filters["lead_id"] = lead_id
        if contact_id: filters["contact_id"] = contact_id
        if deal_id: filters["deal_id"] = deal_id
        if company_id: filters["company_id"] = company_id
        if search: filters["search"] = search
        if associated_type: filters["associated_type"] = associated_type
        if due_date_from: filters["due_date_from"] = due_date_from
        if due_date_to: filters["due_date_to"] = due_date_to
        
        tasks, total = await TaskService.get_tasks(
            tenant_id, filters, page, limit, sort_by, sort_order
        )
        
        # Serialize tasks and resolve associated records
        serialized_tasks = []
        for t in tasks:
            task_dict = await serialize_task(t)
            if t.lead_id or t.contact_id or t.deal_id or t.company_id:
                name, mod = await resolve_associated_record(t)
                task_dict["associated_name"] = name
                task_dict["associated_type"] = mod
                task_dict["associated_id"] = await resolve_associated_id(t)
            serialized_tasks.append(task_dict)
        
        return {
            "tasks": serialized_tasks,
            "total": total,
            "page": page,
            "limit": limit
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("", summary="Create Task", status_code=status.HTTP_201_CREATED)
async def create_task(data: TaskCreateRequest, current_user=Depends(verify_platform_admin)):
    try:
        user_id = UUID(current_user.get('sub'))
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        task = await TaskService.create_task(data.model_dump(), user_id, tenant_id)
        return {"message": "Task created successfully", "task_id": str(task.id)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{task_id}", summary="Get Task Details")
async def get_task_details(task_id: str, current_user=Depends(verify_platform_admin)):
    try:
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        task = await TaskService.get_task(UUID(task_id), tenant_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        task_dict = await serialize_task(task)
        if task.lead_id or task.contact_id or task.deal_id or task.company_id:
            name, mod = await resolve_associated_record(task)
            task_dict["associated_name"] = name
            task_dict["associated_type"] = mod
            task_dict["associated_id"] = await resolve_associated_id(task)
        return task_dict
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid task ID format")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{task_id}", summary="Update Task")
async def update_task(task_id: str, data: TaskUpdateRequest, current_user=Depends(verify_platform_admin)):
    try:
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        user_id = UUID(current_user.get('sub'))
        task = await TaskService.update_task(UUID(task_id), data.model_dump(exclude_none=True), tenant_id, user_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        return {"message": "Task updated successfully", "task": await serialize_task(task)}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid task ID format")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{task_id}", summary="Delete Task")
async def delete_task(task_id: str, current_user=Depends(verify_platform_admin)):
    try:
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        deleted = await TaskService.delete_task(UUID(task_id), tenant_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Task not found")
        return {"message": "Task deleted successfully"}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid task ID format")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Task Actions ──

@router.patch("/{task_id}/complete", summary="Complete Task")
async def complete_task(task_id: str, current_user=Depends(verify_platform_admin)):
    try:
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        task = await TaskService.complete_task(UUID(task_id), tenant_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        return {"message": "Task completed successfully", "task": await serialize_task(task)}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid task ID format")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/{task_id}/status", summary="Update Task Status")
async def update_task_status(task_id: str, status: str = Query(...), current_user=Depends(verify_platform_admin)):
    try:
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        valid_statuses = ["not_started", "in_progress", "waiting", "completed", "cancelled"]
        if status not in valid_statuses:
            raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}")
        task = await TaskService.update_task_status(UUID(task_id), status, tenant_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        return {"message": "Task status updated", "task": await serialize_task(task)}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid task ID format")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/{task_id}/priority", summary="Update Task Priority")
async def update_task_priority(task_id: str, priority: str = Query(...), current_user=Depends(verify_platform_admin)):
    try:
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        valid_priorities = ["high", "medium", "low", "urgent"]
        if priority not in valid_priorities:
            raise HTTPException(status_code=400, detail=f"Invalid priority. Must be one of: {', '.join(valid_priorities)}")
        task = await TaskService.update_task_priority(UUID(task_id), priority, tenant_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        return {"message": "Task priority updated", "task": await serialize_task(task)}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid task ID format")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{task_id}/duplicate", summary="Duplicate Task")
async def duplicate_task(task_id: str, current_user=Depends(verify_platform_admin)):
    try:
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        user_id = UUID(current_user.get('sub'))
        task = await TaskService.duplicate_task(UUID(task_id), tenant_id, user_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        return {"message": "Task duplicated successfully", "task_id": str(task.id)}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid task ID format")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{task_id}/archive", summary="Archive Task")
async def archive_task(task_id: str, current_user=Depends(verify_platform_admin)):
    try:
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        task = await TaskService.archive_task(UUID(task_id), tenant_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        return {"message": "Task archived successfully"}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid task ID format")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Comments ──

@router.post("/{task_id}/comment", summary="Add Comment")
async def add_comment(task_id: str, data: TaskCommentRequest, current_user=Depends(verify_platform_admin)):
    try:
        user_id = UUID(current_user.get('sub'))
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        task = await TaskService.add_comment(UUID(task_id), tenant_id, user_id, data.text, data.mentions, data.parent_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        return {"message": "Comment added", "comments": task.comments}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid task ID format")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{task_id}/comment/{comment_id}", summary="Update Comment")
async def update_comment(task_id: str, comment_id: str, data: TaskCommentRequest, current_user=Depends(verify_platform_admin)):
    try:
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        task = await TaskService.update_comment(UUID(task_id), comment_id, tenant_id, data.text)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        return {"message": "Comment updated", "comments": task.comments}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid task ID format")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{task_id}/comment/{comment_id}", summary="Delete Comment")
async def delete_comment(task_id: str, comment_id: str, current_user=Depends(verify_platform_admin)):
    try:
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        task = await TaskService.delete_comment(UUID(task_id), comment_id, tenant_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        return {"message": "Comment deleted", "comments": task.comments}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid task ID format")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Attachments ──

@router.post("/{task_id}/attachment", summary="Upload Attachment")
async def upload_attachment(task_id: str, file: UploadFile = File(...), current_user=Depends(verify_platform_admin)):
    try:
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        
        task_dir = os.path.join(TASK_ATTACHMENTS_DIR, task_id)
        os.makedirs(task_dir, exist_ok=True)
        
        safe_filename = file.filename.replace(" ", "_")
        file_path = os.path.join(task_dir, safe_filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        file_size_bytes = os.path.getsize(file_path)
        file_size_str = f"{round(file_size_bytes / 1024, 1)} KB" if file_size_bytes < 1024 * 1024 else f"{round(file_size_bytes / (1024 * 1024), 2)} MB"
        file_url = f"/static/task_attachments/{task_id}/{safe_filename}"
        
        task = await TaskService.add_attachment(
            UUID(task_id), tenant_id, safe_filename, file_url,
            file_size_str, file.content_type or "application/octet-stream"
        )
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        
        return {
            "message": "File uploaded successfully",
            "file_url": file_url,
            "file_name": safe_filename,
            "file_size": file_size_str,
            "file_type": file.content_type,
            "attachments": task.attachments
        }
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid task ID format")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{task_id}/attachment/{attachment_id}", summary="Delete Attachment")
async def delete_attachment(task_id: str, attachment_id: str, current_user=Depends(verify_platform_admin)):
    try:
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        task = await TaskService.delete_attachment(UUID(task_id), attachment_id, tenant_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        return {"message": "Attachment deleted", "attachments": task.attachments}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid task ID format")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Checklist ──

@router.put("/{task_id}/checklist", summary="Update Checklist")
async def update_checklist(task_id: str, checklist: list, current_user=Depends(verify_platform_admin)):
    try:
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        task = await TaskService.update_checklist(UUID(task_id), tenant_id, checklist)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        return {"message": "Checklist updated", "checklist": task.checklist}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid task ID format")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Workspace ──

@router.get("/{task_id}/workspace", summary="Get Task Workspace")
async def get_task_workspace(task_id: str, current_user=Depends(verify_platform_admin)):
    try:
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        workspace = await TaskService.get_workspace_task(UUID(task_id), tenant_id)
        if not workspace:
            raise HTTPException(status_code=404, detail="Task not found")
        return workspace
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid task ID format")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))